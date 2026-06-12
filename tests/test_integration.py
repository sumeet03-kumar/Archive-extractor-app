import io
import time

import pytest

from app import db as _db, Job

def wait_for_job(client, job_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f'/extractions/{job_id}')
        data = response.get_json()

        if data['status'] in ('completed', 'failed'):
            return data
        
        time.sleep(0.1)
    raise TimeoutError(f"Job {job_id!r} did not reach a terminal state within {timeout}s")
    
class TestFullExtractionFlow:
    def test_full_flow(self, client, make_zip):
        archive = make_zip({
            'report.txt': 'This is a report.',
            'data.csv': 'id,value\n1,100\n2,200',
        })
        data = {
            'pattern': '*.txt',
            'archive': (io.BytesIO(archive), 'test.zip')
        }

        submit_resp = client.post('/extractions', data=data, content_type='multipart/form-data')
        assert submit_resp.status_code == 202

        job_id = submit_resp.get_json()['job_id']
        job_data = wait_for_job(client, job_id)

        assert job_data['status'] == 'completed'
        assert job_data['matches'] == 1

        results_resp = client.get(f'/extractions/{job_id}/results')
        assert results_resp.status_code == 200
        body = results_resp.get_json()
        assert body['total_count'] == 1
        assert body['results'][0]['file_name'] == 'report.txt'

    def test_pattern_filters_correctly(self, client, make_zip):
        archive = make_zip({
            'notes.txt': 'Notes',
            'summary.txt': 'Summary',
            'data.csv': 'id,value\n1,100\n2,200',
            'document.md': '# Document'
        })
        data = {
            'pattern': '*.txt',
            'archive': (io.BytesIO(archive), 'test.zip')
        }

        submit_resp = client.post('/extractions', data=data, content_type='multipart/form-data')
        assert submit_resp.status_code == 202

        job_id = submit_resp.get_json()['job_id']
        job_data = wait_for_job(client, job_id)

        assert job_data['status'] == 'completed'
        assert job_data['matches'] == 2

        results_resp = client.get(f'/extractions/{job_id}/results')
        assert results_resp.status_code == 200
        body = results_resp.get_json()
        file_names = {r['file_name'] for r in body['results']}
        assert file_names == {'notes.txt', 'summary.txt'}

    def test_health_check_returns_ok(self, client):
        response = client.get('/health')
        body = response.get_json()
        assert response.status_code == 200
        assert body['status'] == 'ok'
