import pytest
import os
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from app import ArchiveExtractor


@pytest.fixture
def sample_zip_archive():
    temp_dir = tempfile.mkdtemp()
    test_file1 = os.path.join(temp_dir, 'test1.txt')
    test_file2_dir = os.path.join(temp_dir, 'subdir')
    os.makedirs(test_file2_dir, exist_ok=True)
    with open(test_file1, 'w') as f:
        f.write('test content 1')
    with open(os.path.join(test_file2_dir, 'test2.txt'), 'w') as f:
        f.write('test content 2')
    zip_path = os.path.join(temp_dir, 'test_archive.zip')
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        zipf.write(test_file1, arcname='test1.txt')
        zipf.write(os.path.join(test_file2_dir, 'test2.txt'), arcname='subdir/test2.txt')
    yield zip_path
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)

@pytest.fixture
def executor():
    ex = ThreadPoolExecutor(max_workers=2)
    yield ex
    ex.shutdown()


def test_is_archive_zip(executor):
    extractor = ArchiveExtractor(executor=executor)
    assert extractor.is_archive('test.zip') is True
    assert extractor.is_archive('test.ZIP') is True


def test_is_archive_tar(executor):
    extractor = ArchiveExtractor(executor=executor)
    assert extractor.is_archive('test.tar') is True
    assert extractor.is_archive('test.tar.gz') is True
    assert extractor.is_archive('test.tgz') is True


def test_is_archive_non_archive(executor):
    extractor = ArchiveExtractor(executor=executor)
    assert extractor.is_archive('test.txt') is False
    assert extractor.is_archive('test.pdf') is False


def test_matches_pattern_simple(executor):
    extractor = ArchiveExtractor(executor=executor)
    assert extractor.matches_pattern('test.txt', '*.txt') is True
    assert extractor.matches_pattern('test.pdf', '*.txt') is False


def test_extract_zip_archive(sample_zip_archive, executor):
    with ArchiveExtractor(executor=executor) as extractor:
        extracted_dir = extractor.extract_archive(sample_zip_archive)
        assert os.path.exists(extracted_dir)
        assert os.path.exists(os.path.join(extracted_dir, 'test1.txt'))
        assert os.path.exists(os.path.join(extracted_dir, 'subdir', 'test2.txt'))


def test_extract_and_find_zip(sample_zip_archive, executor):
    with ArchiveExtractor(executor=executor) as extractor:
        import threading
        threading.Thread(target=extractor.run, args=(sample_zip_archive, '*.txt', 'test.zip')).start()
        results = []
        while True:
            res = extractor.results_queue.get()
            if res is None:
                break
            results.append(res)
        assert len(results) == 2
        assert any(r['file_name'] == 'test1.txt' for r in results)
        assert any(r['file_name'] == 'test2.txt' for r in results)


def test_cleanup(sample_zip_archive, executor):
    with ArchiveExtractor(executor=executor) as extractor:
        extracted_dir = extractor.extract_archive(sample_zip_archive)
        assert os.path.exists(extracted_dir)
    assert not os.path.exists(extracted_dir)
