import uuid
import logging
import shutil
import tempfile
import tarfile
import zipfile
import fnmatch
import threading
import queue
from pathlib import Path
from flask import Flask, request, jsonify
import os
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Integer, String, ForeignKey, DateTime, Text, text
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from werkzeug.utils import secure_filename

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Config:
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = int(os.getenv('DB_PORT', 5432))
    DB_NAME = os.getenv('DB_NAME', 'extractor')
    DB_USER = os.getenv('DB_USER', 'postgres')
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'password')
    PORT = int(os.getenv('PORT', 5000))

    JOB_CONCURRENCY = int(os.getenv('JOB_CONCURRENCY', 4))
    EXTRACTION_CONCURRENCY = int(os.getenv('EXTRACTION_CONCURRENCY', 8))

    MAX_NESTED_LEVEL = int(os.getenv('MAX_NESTED_LEVEL', 10))

    SQLALCHEMY_DATABASE_URI = (
        f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
    )

app = Flask(__name__)
app.config.from_object(Config)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ==================== Executors ====================

job_executor = ThreadPoolExecutor(max_workers=Config.JOB_CONCURRENCY)
extraction_executor = ThreadPoolExecutor(max_workers=Config.EXTRACTION_CONCURRENCY)

logger.info(f"Job executor started with {Config.JOB_CONCURRENCY} workers")
logger.info(f"Extraction executor started with {Config.EXTRACTION_CONCURRENCY} workers")

# ==================== Database Models ====================

class Job(db.Model):
    __tablename__ = 'jobs'

    id = db.Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status = db.Column(String(20), nullable=False, default='pending')
    pattern = db.Column(String(255), nullable=False)
    archive_name = db.Column(String(255), nullable=False)
    created_at = db.Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(DateTime, nullable=True)
    error = db.Column(Text, nullable=True)
    matches = db.Column(Integer, default=0)

    results = db.relationship('Result', back_populates='job', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': str(self.id),
            'status': self.status,
            'pattern': self.pattern,
            'archive_name': self.archive_name,
            'created_at': self.created_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'error': self.error,
            'matches': self.matches
        }

class Result(db.Model):
    __tablename__ = 'results'

    id = db.Column(Integer, primary_key=True, autoincrement=True)
    job_id = db.Column(String(36), ForeignKey('jobs.id'), nullable=False)
    file_path = db.Column(String(1024), nullable=False)
    file_name = db.Column(String(255), nullable=False)
    file_size = db.Column(Integer, nullable=False)
    nesting_level = db.Column(Integer, nullable=False)
    source_archive = db.Column(String(255), nullable=False)
    extracted_at = db.Column(DateTime, nullable=False, default=datetime.utcnow)

    job = db.relationship('Job', back_populates='results')

    def to_dict(self):
        return {
            'id': self.id,
            'job_id': str(self.job_id),
            'file_path': self.file_path,
            'file_name': self.file_name,
            'file_size': self.file_size,
            'nesting_level': self.nesting_level,
            'source_archive': self.source_archive,
            'extracted_at': self.extracted_at.isoformat()
        }

def init_db():
    with app.app_context():
        db.create_all()
    logger.info("Database initialized successfully.")

# ==================== Archive Extractor ====================

class ArchiveExtractor:
    SUPPORTED_EXTENSIONS = {
        '.zip', '.tar', '.gz', '.tgz',
        '.bz2', '.tar.gz', '.tar.bz2'
    }

    def __init__(self, executor, max_depth=10):
        self.max_depth = max_depth
        self.executor = executor
        self.temp_dirs = []
        self._temp_dirs_lock = threading.Lock()
        self.results_queue = queue.Queue()

        self._futures = set()
        self._futures_lock = threading.Lock()
        self._all_done = threading.Condition()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.cleanup()

    def cleanup(self):
        with self._temp_dirs_lock:
            for temp_dir in self.temp_dirs:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
            self.temp_dirs = []

    def is_archive(self, file_path):
        file_lower = file_path.lower()
        if file_lower.endswith(('.tar.gz', '.tar.bz2', '.tgz')):
            return True
        return Path(file_path).suffix.lower() in self.SUPPORTED_EXTENSIONS

    def _safe_extract_tar(self, tar, target_dir):
        """Extract tar safely, blocking path traversal (Zip Slip) and symlink escapes."""
        abs_target = os.path.realpath(target_dir)
        prefix = abs_target + os.sep

        for member in tar.getmembers():
            member_path = os.path.realpath(os.path.join(abs_target, member.name))
            if member_path != abs_target and not member_path.startswith(prefix):
                raise ValueError(
                    f"Path traversal detected in tar archive: {member.name!r}"
                )
            if member.issym() or member.islnk():
                link_path = os.path.realpath(
                    os.path.join(os.path.dirname(member_path), member.linkname)
                )
                if not link_path.startswith(prefix):
                    raise ValueError(
                        f"Symlink escape detected in tar archive: "
                        f"{member.name!r} -> {member.linkname!r}"
                    )
        tar.extractall(path=target_dir)

    def _safe_extract_zip(self, zip_ref, target_dir):
        """Extract zip safely, blocking path traversal (Zip Slip)."""
        abs_target = os.path.realpath(target_dir)
        prefix = abs_target + os.sep

        for member in zip_ref.namelist():
            member_path = os.path.realpath(os.path.join(abs_target, member))
            if member_path != abs_target and not member_path.startswith(prefix):
                raise ValueError(
                    f"Path traversal detected in zip archive: {member!r}"
                )
        zip_ref.extractall(path=target_dir)

    def extract_archive(self, archive_path):
        temp_dir = tempfile.mkdtemp(prefix='archive_extract_')
        with self._temp_dirs_lock:
            self.temp_dirs.append(temp_dir)

        file_lower = archive_path.lower()

        if file_lower.endswith(('.tar.gz', '.tgz')):
            with tarfile.open(archive_path, 'r:gz') as tar:
                self._safe_extract_tar(tar, temp_dir)
        elif file_lower.endswith('.tar.bz2'):
            with tarfile.open(archive_path, 'r:bz2') as tar:
                self._safe_extract_tar(tar, temp_dir)
        elif file_lower.endswith('.tar'):
            with tarfile.open(archive_path, 'r') as tar:
                self._safe_extract_tar(tar, temp_dir)
        elif file_lower.endswith('.zip'):
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                self._safe_extract_zip(zip_ref, temp_dir)
        else:
            raise ValueError(f"Unsupported archive format: {archive_path}")

        return temp_dir

    def matches_pattern(self, file_path, pattern):
        normalized_path = file_path.replace('\\', '/')
        return fnmatch.fnmatch(normalized_path, pattern)

    def _submit_task(self, *args, **kwargs):
        future = self.executor.submit(self.process_archive_task, *args, **kwargs)
        with self._futures_lock:
            self._futures.add(future)
        future.add_done_callback(self._task_done)

    def _task_done(self, future):
        with self._futures_lock:
            self._futures.discard(future)
            if not self._futures:
                with self._all_done:
                    self._all_done.notify_all()

    def process_archive_task(
        self, archive_path, pattern,
        source_archive_name, depth=0, parent_path=''
    ):
        if depth > self.max_depth:
            return

        try:
            extracted_dir = self.extract_archive(archive_path)

            for root, _, files in os.walk(extracted_dir):
                for file in files:
                    full_file_path = os.path.join(root, file)
                    relative_file_path = os.path.relpath(full_file_path, extracted_dir)

                    nested_path = (
                        f"{parent_path}/{relative_file_path}"
                        if parent_path else relative_file_path
                    )

                    if self.matches_pattern(nested_path, pattern):
                        file_size = os.path.getsize(full_file_path)
                        self.results_queue.put({
                            'file_path': nested_path,
                            'file_name': file,
                            'file_size': file_size,
                            'nesting_depth': depth,
                            'source_archive': source_archive_name
                        })

                    if self.is_archive(full_file_path) and depth < self.max_depth:
                        self._submit_task(
                            archive_path=full_file_path,
                            pattern=pattern,
                            source_archive_name=source_archive_name,
                            depth=depth + 1,
                            parent_path=nested_path
                        )

        except Exception as e:
            logger.error(f"Error processing {archive_path}: {e}")

    def run(self, archive_path, pattern, source_archive_name):
        self._submit_task(
            archive_path=archive_path,
            pattern=pattern,
            source_archive_name=source_archive_name,
            depth=0,
            parent_path=''
        )

        with self._all_done:
            while True:
                with self._futures_lock:
                    if not self._futures:
                        break
                self._all_done.wait()

        self.results_queue.put(None)

# ==================== Job Processing ====================

def process_extraction_job(job_id, archive_path, pattern):
    with app.app_context():
        try:
            job = Job.query.filter_by(id=job_id).first()
            if not job:
                return

            job.status = 'processing'
            db.session.commit()

            matches_count = 0

            with ArchiveExtractor(
                executor=extraction_executor,
                max_depth=Config.MAX_NESTED_LEVEL
            ) as extractor:

                extractor.run(archive_path, pattern, job.archive_name)

                while True:
                    result = extractor.results_queue.get()
                    if result is None:
                        break

                    db_result = Result(
                        job_id=job_id,
                        file_path=result['file_path'],
                        file_name=result['file_name'],
                        file_size=result['file_size'],
                        nesting_level=result['nesting_depth'],
                        source_archive=result['source_archive'],
                        extracted_at=datetime.utcnow()
                    )

                    db.session.add(db_result)
                    matches_count += 1

                    if matches_count % 100 == 0:
                        db.session.commit()

            job.status = 'completed'
            job.matches = matches_count
            job.completed_at = datetime.utcnow()
            db.session.commit()

        except Exception as e:
            logger.error(f"[Job {job_id}] Error: {e}")
            db.session.rollback()

            job = Job.query.filter_by(id=job_id).first()
            if job:
                job.status = 'failed'
                job.error = str(e)
                job.completed_at = datetime.utcnow()
                db.session.commit()
        finally:
            if os.path.exists(archive_path):
                os.remove(archive_path)

# ==================== Routes ====================

@app.route('/health', methods=['GET'])
def health_check():
    try:
        db.session.execute(text('SELECT 1'))
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/extractions', methods=['POST'])
def submit_extraction():
    try:
        pattern = request.form.get('pattern')
        archive_file = request.files.get('archive')

        if not pattern or not archive_file:
            return jsonify({'error': 'Missing pattern or archive'}), 400

        secure_name = secure_filename(archive_file.filename)
        archive_path = os.path.join(
            tempfile.gettempdir(),
            f"{uuid.uuid4()}_{secure_name}"
        )
        archive_file.save(archive_path)

        job = Job(
            id=str(uuid.uuid4()),
            status='pending',
            pattern=pattern,
            archive_name=secure_name,
            created_at=datetime.utcnow()
        )

        db.session.add(job)
        db.session.commit()

        job_executor.submit(
            process_extraction_job,
            job.id,
            archive_path,
            pattern
        )

        return jsonify({
            'job_id': job.id,
            'status': 'pending'
        }), 202

    except Exception as e:
        logger.error(f"Submit error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/extractions/<job_id>', methods=['GET'])
def get_job_status(job_id):
    job = Job.query.filter_by(id=job_id).first()
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(job.to_dict())

@app.route('/extractions/<job_id>/results', methods=['GET'])
def get_job_results(job_id):
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    results_query = Result.query.filter_by(job_id=job_id)
    total_count = results_query.count()

    results = results_query.offset(
        (page - 1) * per_page
    ).limit(per_page).all()

    return jsonify({
        'job_id': job_id,
        'total_count': total_count,
        'page': page,
        'per_page': per_page,
        'total_pages': (total_count + per_page - 1) // per_page,
        'results': [r.to_dict() for r in results]
    })

# ==================== Main ====================

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=Config.PORT)
