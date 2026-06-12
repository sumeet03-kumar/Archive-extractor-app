import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import io
import os
import tarfile
import tempfile
import zipfile


_db_fd, _TEST_DB_PATH = tempfile.mkstemp(suffix='_test.db')
os.close(_db_fd)
os.environ.setdefault('SQLALCHEMY_DATABASE_URI', f'sqlite:///{_TEST_DB_PATH}')

import pytest
from sqlalchemy import delete
from app import app as flask_app
from app import db as _db
from app import Result, Job


@pytest.fixture(scope='session')
def app():
    flask_app.config['TESTING'] = True

    with flask_app.app_context():
        _db.create_all()

    yield flask_app

    with flask_app.app_context():
        _db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture(autouse=True)
def clean_tables(app):
    yield
    with app.app_context():
        _db.session.execute(delete(Result))
        _db.session.execute(delete(Job))
        _db.session.commit()






@pytest.fixture
def make_zip():
    def _factory(files=None):
        if files is None:
            files = {'test.txt': b'This is a test file.'}
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            for name, content in files.items():
                if isinstance(content, str):
                    content = content.encode()
                zf.writestr(name, content)
        return buf.getvalue()
    return _factory

@pytest.fixture
def make_tar_gz():
    def _factory(files=None):
        if files is None:
            files = {'test.txt': b'This is a test file.'}
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w:gz') as tar:
            for name, content in files.items():
                if isinstance(content,str):
                    content = content.encode()
                info = tarfile.TarInfo(name)
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))
        return buf.getvalue()
    return _factory