import pytest
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor
from app import ArchiveExtractor

class TestExtractArchive:
    @pytest.fixture(autouse=True)
    def extractor(self):
        self._executor = ThreadPoolExecutor(max_workers=2)
        self.ext = ArchiveExtractor(self._executor, max_depth=2)
        yield
        self.ext.cleanup()
        self._executor.shutdown(wait=False)

    def test_extract_zip_produces_files(self, make_zip, tmp_path):
        archive = tmp_path / 'test.zip'
        archive.write_bytes(make_zip({'file1.txt': 'Content of file 1', 'sub/file2.txt': 'Content of file 2'}))
        
        extracted = self.ext.extract_archive(str(archive))

        with open(os.path.join(extracted, 'file1.txt')) as f:
            assert f.read() == 'Content of file 1'

        assert os.path.isdir(extracted)
        assert os.path.exists(os.path.join(extracted, 'file1.txt'))
        assert os.path.exists(os.path.join(extracted, 'sub', 'file2.txt'))

    def test_extract_tar_gz_produces_files(self, make_tar_gz, tmp_path):
        archive = tmp_path / 'test.tar.gz'
        archive.write_bytes(make_tar_gz({'file1.txt': 'Content of file'}))

        extracted = self.ext.extract_archive(str(archive))

        assert os.path.isdir(extracted)
        assert os.path.exists(os.path.join(extracted, 'file1.txt'))

    def test_extract_nested_archives(self, make_zip, tmp_path):
        inner_bytes = make_zip({'inner.txt': 'Inner content'})

        outer = tmp_path / 'outer.zip'

        with zipfile.ZipFile(str(outer), 'w') as zf:
            zf.writestr('nested.zip', inner_bytes)
            zf.writestr('root.txt', 'root content')

        self.ext.run(str(outer), pattern='*.txt', source_archive_name='outer.zip')

        results = []
        while True:
            item = self.ext.results_queue.get()
            if item is None:
                break
            results.append(item)

        assert any(r['file_name'] == 'root.txt' and r['nesting_depth'] == 0 for r in results)
        assert any(r['file_name'] == 'inner.txt' and r['nesting_depth'] == 1 for r in results)

    def test_unsupported_format(self, tmp_path):
        archive = tmp_path / 'test.rar'
        archive.write_bytes(b'Not a real archive')

        with pytest.raises(ValueError, match='Unsupported archive format'):
            self.ext.extract_archive(str(archive))

    def test_cleanup_removes_extracted_dirs(self, make_zip, tmp_path):
        archive = tmp_path / 'test.zip'
        archive.write_bytes(make_zip({'file.txt': 'Content'}))

        extracted = self.ext.extract_archive(str(archive))
        assert os.path.isdir(extracted)

        self.ext.cleanup()

        assert not os.path.exists(extracted)
        assert self.ext.temp_dirs == []


class TestArchiveExtractorRun:
    def _collect_results(self, extractor, timeout=10):
        items = []
        while True:
            item = extractor.results_queue.get(timeout=timeout)
            if item is None:
                break
            items.append(item)
        return items
    
    def test_run_returns_matching_files(self, make_zip, tmp_path):
        archive = tmp_path / 'test.zip'
        archive.write_bytes(make_zip({'file1.txt': 'Content of file 1', 'file2.log': 'Log content'}))

        executor = ThreadPoolExecutor(max_workers=2)
        with ArchiveExtractor(executor=executor, max_depth=2) as ext:
            ext.run(str(archive), pattern='*.txt', source_archive_name='test.zip')
            results = self._collect_results(ext)

        assert len(results) == 1
        assert results[0]['file_name'] == 'file1.txt'
        assert results[0]['source_archive'] == 'test.zip'
        assert results[0]['nesting_depth'] == 0
    
    def test_run_returns_no_results_when_no_matches(self, make_zip, tmp_path):
        archive = tmp_path / 'test.zip'
        archive.write_bytes(make_zip({'file1.txt': 'Content of file 1', 'file2.log': 'Log content'}))

        executor = ThreadPoolExecutor(max_workers=2)
        with ArchiveExtractor(executor=executor, max_depth=2) as ext:
            ext.run(str(archive), pattern='*.json', source_archive_name='test.zip')
            results = self._collect_results(ext)

        assert len(results) == 0

    def test_run_returns_all_matching_files(self, make_zip, tmp_path):
        archive = tmp_path / 'test.zip'
        archive.write_bytes(make_zip({
            'file1.txt': 'First File',
            'file2.txt': 'Second File',
            'file3.txt': 'Third File',
            'skip.json': 'Should be skipped'
        }))

        executor = ThreadPoolExecutor(max_workers=2)
        with ArchiveExtractor(executor=executor, max_depth=2) as ext:
            ext.run(str(archive), pattern='*.txt', source_archive_name='test.zip')
            results = self._collect_results(ext)

        assert len(results) == 3
        names = {r['file_name'] for r in results}
        assert names == {'file1.txt', 'file2.txt', 'file3.txt'}
