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
