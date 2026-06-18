import io
from datetime import datetime
from unittest.mock import patch

import pytest

from app import db as _db
from app import Job, Result



# POST /extractions

class TestSubmitExtraction:
    def test_missing_pattern_returns_400(self, client, make_zip):
        data = {'archive': (io.BytesIO(make_zip({'file.txt': 'Content'})), 'test.zip')}
        response = client.post('/extractions', data=data, content_type='multipart/form-data')
        assert response.status_code == 400
        assert 'error' in response.get_json()

    def test_missing_archive_returns_400(self, client):
        data = {'pattern': '*.txt'}
        response = client.post('/extractions', data=data, content_type='multipart/form-data')
        assert response.status_code == 400
        assert 'error' in response.get_json()

    def test_valid_submission_returns_202(self, client, make_zip):
        with patch('app.job_executor'):
            data = {
                'pattern': '*.txt',
                'archive': (io.BytesIO(make_zip({'file.txt': 'Content'})), 'test.zip')
            }
            response = client.post('/extractions', data=data, content_type='multipart/form-data')
        assert response.status_code == 202

    def test_valid_submission_returns_job_id_and_status(self, client, make_zip):
        with patch('app.job_executor'):
            data = {
                'pattern': '*.txt',
                'archive': (io.BytesIO(make_zip({'file.txt': 'Content'})), 'test.zip')
            }
            response = client.post('/extractions', data=data, content_type='multipart/form-data')

        body = response.get_json()
        assert 'job_id' in body
        assert body['status'] == 'pending'

    def test_valid_submission_creates_job_in_db(self, client, app, make_zip):
        with patch('app.job_executor'):
            data = {
                'pattern': '*.txt',
                'archive': (io.BytesIO(make_zip({'file.txt': 'Content'})), 'test.zip')
            }
            response = client.post('/extractions', data=data, content_type='multipart/form-data')

        job_id = response.get_json()['job_id']
        with app.app_context():
            job = _db.session.get(Job, job_id)
        
        assert job is not None
        assert job.status == 'pending'
        assert job.pattern == '*.txt'
        assert job.archive_name == 'test.zip'

    def test_valid_submission_triggers_background_job(self, client, make_zip):
        with patch('app.job_executor') as mock_executor:
            data = {
                'pattern': '*.txt',
                'archive': (io.BytesIO(make_zip({'file.txt': 'Content'})), 'test.zip')
            }
            client.post('/extractions', data=data, content_type='multipart/form-data')

        mock_executor.submit.assert_called_once()

    def test_empty_pattern_returns_400(self, client, make_zip):
        data = {
            'pattern': '',
            'archive': (io.BytesIO(make_zip({'file.txt': 'Content'})), 'test.zip')
        }
        response = client.post('/extractions', data=data, content_type='multipart/form-data')
        assert response.status_code == 400
        assert 'error' in response.get_json()

    def test_exception_during_submission_returns_500(self, client, make_zip):
        with patch('app.db.session.commit', side_effect=Exception('Database error')):
            data = {
                'pattern': '*.txt',
                'archive': (io.BytesIO(make_zip({'file.txt': 'Content'})), 'test.zip')
            }
            response = client.post('/extractions', data=data, content_type='multipart/form-data')
        
        assert response.status_code == 500
        body = response.get_json()
        assert 'error' in body
        assert 'Database error' in body['error']


# GET /extractions/<job_id>
class TestGetJobStatus:
    def test_nonexistent_job_returns_404(self, client):
        response = client.get('/extractions/9999')
        assert response.status_code == 404
        assert 'error' in response.get_json()

    def test_known_job_returns_200_with_status(self, client, app):
        with app.app_context():
            job = Job(id='status-job-1', pattern='*.txt', archive_name='test.zip', status='pending')
            _db.session.add(job)
            _db.session.commit()

            job_id = job.id

        response = client.get(f'/extractions/{job_id}')
        body = response.get_json()
        assert response.status_code == 200
        assert body['id'] == job_id
        assert body['status'] == 'pending'

    def test_returned_body_contains_all_fields(self, client,app):
        with app.app_context():
            job = Job(
                id='status-job-2',
                status='completed',
                pattern='*.json',
                archive_name='test.zip',
                created_at=datetime(2024, 1, 15, 9, 0, 0),
                completed_at=datetime(2024, 1, 15, 9, 30, 0),
                matches=7,
            )
            _db.session.add(job)
            _db.session.commit()

            job_id = job.id

        response = client.get(f'/extractions/{job_id}')
        body = response.get_json()
        assert body['id'] == 'status-job-2'
        assert body['status'] == 'completed'
        assert body['pattern'] == '*.json'
        assert body['archive_name'] == 'test.zip'
        assert body['created_at'] == '2024-01-15T09:00:00'
        assert body['completed_at'] == '2024-01-15T09:30:00'
        assert body['matches'] == 7

    def test_pending_job_has_null_completed_at(self, client, app):
        with app.app_context():
            job = Job(
                id='status-job-3',
                status='pending',
                pattern='*.log',
                archive_name='test.zip',
                created_at=datetime(2024, 1, 15, 10, 0, 0),
            )
            _db.session.add(job)
            _db.session.commit()

            job_id = job.id

        response = client.get(f'/extractions/{job_id}')
        body = response.get_json()
        assert body['completed_at'] is None

    def test_failed_job_includes_error_field(self, client, app):
        with app.app_context():
            job = Job(
                id='status-job-4',
                status='failed',
                pattern='*.txt',
                archive_name='test.zip',
                error='Corrupt archive',
                created_at=datetime(2024, 1, 15, 10, 0, 0),
                completed_at=datetime(2024, 1, 15, 10, 1, 0),
            )
            _db.session.add(job)
            _db.session.commit()

        response = client.get('/extractions/status-job-4')
        body = response.get_json()
        assert response.status_code == 200
        assert body['status'] == 'failed'
        assert body['error'] == 'Corrupt archive'

# GET /extractions/<job_id>/results

class TestGetJobResults:
    def _seed_job_with_results(self, app, job_id, count):
        with app.app_context():
            job = Job(
                id=job_id,
                status='completed',
                pattern='*.txt',
                archive_name='test.zip',
                created_at=datetime.utcnow(),
                matches=count
            )
            _db.session.add(job)
            _db.session.flush()
            for i in range(count):
                result = Result(
                    job_id=job_id,
                    file_path=f'file_{i}.txt',
                    file_name=f'file_{i}.txt',
                    file_size=100 + i,
                    nesting_level=0,
                    source_archive='test.zip',
                    extracted_at=datetime.utcnow()
                )
                _db.session.add(result)
            _db.session.commit()

    def test_nonexistent_job_returns_404(self,client):
        response = client.get('/extractions/non-existent-job/results')
        assert response.status_code == 404
        assert 'error' in response.get_json()

    def test_returns_correct_structure(self, client, app):
        self._seed_job_with_results(app, 'struct-job', 3)

        response = client.get('/extractions/struct-job/results')
        body = response.get_json()

        assert 'job_id' in body
        assert 'total_count' in body
        assert 'page' in body
        assert 'per_page' in body
        assert 'total_pages' in body
        assert 'results' in body

    def test_pending_job_returns_202(self, client, app):
        with app.app_context():
            job = Job(
                id='pending-results-job',
                status='pending',
                pattern='*.txt',
                archive_name='test.zip'
            )
            _db.session.add(job)
            _db.session.commit()
        
        response = client.get('/extractions/pending-results-job/results')
        assert response.status_code == 202
        assert 'error' in response.get_json()

    def test_processing_job_returns_202(self, client, app):
        with app.app_context():
            job = Job(
                id='processing-results-job',
                status='pending',
                pattern='*.txt',
                archive_name='test.zip'
            )
            _db.session.add(job)
            _db.session.commit()

        response = client.get('/extractions/processing-results-job/results')
        assert response.status_code == 202
        assert 'error' in response.get_json()

    def test_failed_job_returns_500(self, client, app):
        with app.app_context():
            job = Job(
                id='failed-results-job',
                status='failed',
                pattern='*.txt',
                archive_name='test.zip'
            )
            _db.session.add(job)
            _db.session.commit()
        
        response = client.get('/extractions/failed-results-job/results')
        assert response.status_code == 500
        assert 'error' in response.get_json()

    def test_results_items_contain_correct_fields(self, client, app):
        self._seed_job_with_results(app, 'fields-job', 1)

        response = client.get('/extractions/fields-job/results')
        item = response.get_json()['results'][0]

        assert 'id' in item
        assert 'job_id' in item
        assert 'file_path' in item
        assert 'file_name' in item
        assert 'file_size' in item
        assert 'nesting_level' in item
        assert 'source_archive' in item
        assert 'extracted_at' in item

    def test_completed_job_with_zero_matches_returns_zero_results(self, client, app):
        with app.app_context():
            job = Job(
                id='zero-match-job',
                status='completed',
                pattern='*.txt',
                archive_name='test.zip',
                matches=0
            )
            _db.session.add(job)
            _db.session.commit()

        response = client.get('/extractions/zero-match-job/results')
        body = response.get_json()

        assert response.status_code == 200
        assert body['total_count'] == 0
        assert body['results'] == []
