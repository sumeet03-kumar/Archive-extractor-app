# Archive File Extractor Service

A robust HTTP service for extracting and searching files within archive files (zip, tar, tar.gz, tar.bz2) and nested archives at any depth. Results are persisted to PostgreSQL with full audit trails and accessible via REST API.

## Features

- **Nested Archive Support**: Recursively extracts archives nested at any depth (configurable limit, default: 10 levels)
- **Parallel Processing**: Multi-threaded extraction with shared ThreadPoolExecutor for optimal CPU utilization
- **Memory Efficient**: Queue-based streaming with batch commits (100 results per commit) maintains constant memory usage
- **Glob Pattern Matching**: Flexible file filtering (e.g., `**/*.json`, `src/**/config.*`)
- **Asynchronous Jobs**: Non-blocking job submission with background worker pool
- **Database Persistence**: PostgreSQL storage with comprehensive metadata (path, size, nesting level, source archive, timestamp)
- **RESTful API**: Job submission, status tracking, paginated result retrieval, health checks
- **Docker Ready**: Docker Compose setup for single-command deployment
- **Security**: Path traversal protection (Zip Slip), symlink escape prevention, configurable nesting limits
- **Error Handling**: Graceful failures with automatic cleanup and detailed logging

## Architecture

**Core Components**:
- Flask: HTTP service and REST API
- SQLAlchemy: Database abstraction layer for PostgreSQL
- ArchiveExtractor: Core extraction engine with nested archive support
- ThreadPoolExecutor: Parallel task processing
- Queue-based Producer-Consumer: Memory-efficient result streaming

**Database Models**:
- Job: Extraction job status, pattern, archive name, timestamps, match count, errors
- Result: Individual file matches with metadata (path, size, nesting level, source archive)

**Asynchronous Job Processing Rationale**: In-process ThreadPoolExecutor + Queue avoids external dependencies (no Celery/Redis), simplifies deployment (single process), and provides real-time status updates via database polling. For single-instance deployments with moderate concurrency (default: 4 job workers), this approach balances simplicity, operational overhead, and performance.

## Prerequisites

- Python 3.11+
- PostgreSQL 15+ (or Docker Compose)
- pip for dependency management

## Installation & Quick Start

### Option 1: Docker Compose (Recommended)

```bash
docker-compose up --build
```

This automatically:
- Spins up PostgreSQL 15 container
- Builds and runs Flask application
- Sets up environment variables and networking
- Initializes database with health checks

Service available at `http://localhost:5000`

### Option 2: Local Setup

1. **Create and activate virtual environment**:
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate
```

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

3. **Set environment variables**:
```bash
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=extractor
export DB_USER=postgres
export DB_PASSWORD=password
export PORT=5000
export JOB_CONCURRENCY=4
export EXTRACTION_CONCURRENCY=8
export MAX_NESTED_LEVEL=10
```

4. **Ensure PostgreSQL is running** and create database:
```bash
createdb -U postgres extractor
```

5. **Run application**:
```bash
python app.py
```

## Configuration

Environment variables control behavior:

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | localhost | PostgreSQL host |
| `DB_PORT` | 5432 | PostgreSQL port |
| `DB_NAME` | extractor | Database name |
| `DB_USER` | postgres | Database user |
| `DB_PASSWORD` | password | Database password |
| `PORT` | 5000 | Service port |
| `JOB_CONCURRENCY` | 4 | Concurrent job workers |
| `EXTRACTION_CONCURRENCY` | 8 | Concurrent extraction workers |
| `MAX_NESTED_LEVEL` | 10 | Maximum archive nesting depth |


## API Endpoints

### 1. Health Check
**`GET /health`**

Check service and database connectivity.
```bash
curl http://localhost:5000/health
```

### 2. Submit Extraction Job
**`POST /extractions`**

Submit archive file and pattern to extract matching files.

**Parameters** (form-data):
- `archive` (file): Archive to process (zip, tar, tar.gz, tar.bz2)
- `pattern` (string): Glob pattern for matching (e.g., `*.txt`, `**/*.json`, `src/**/config.*`)

**Design Choice**: Multipart/form-data upload is used for direct file streaming, avoiding URL-based references which would require filesystem access or external I/O. This approach ensures security (no path traversal), simplicity (no external dependencies), and supports large files efficiently through streaming.

```bash
curl -X POST http://localhost:5000/extractions \
  -F "pattern=**/*.json" \
  -F "archive=@myarchive.zip"
```

**Response** (202 Accepted):
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending"
}
```

### 3. Get Job Status
**`GET /extractions/<job_id>`**

Retrieve extraction job status and metadata.

**Status Values**: `pending`, `processing`, `completed`, `failed`

```bash
curl http://localhost:5000/extractions/550e8400-e29b-41d4-a716-446655440000
```

**Response** (200 OK):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "pattern": "*.txt",
  "archive_name": "myarchive.zip",
  "created_at": "2024-01-15T10:30:00",
  "completed_at": "2024-01-15T10:35:00",
  "error": null,
  "matches": 42
}
```

### 4. Get Extraction Results (Paginated)
**`GET /extractions/<job_id>/results?page=1&per_page=20`**

Retrieve paginated results from completed extraction job.

**Query Parameters**:
- `page` (optional, default: 1): Page number
- `per_page` (optional, default: 20, max: 100): Results per page

```bash
curl "http://localhost:5000/extractions/550e8400-e29b-41d4-a716-446655440000/results?page=1&per_page=20"
```

**Response** (200 OK):
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "total_count": 42,
  "page": 1,
  "per_page": 20,
  "total_pages": 3,
  "results": [
    {
      "id": 1,
      "file_path": "config.txt",
      "file_name": "config.txt",
      "file_size": 1024,
      "nesting_level": 0,
      "source_archive": "myarchive.zip",
      "extracted_at": "2024-01-15T10:35:00"
    }
  ]
}
```


## Supported Archive Formats

- **ZIP**: `.zip`
- **TAR**: `.tar`
- **TAR with GZIP**: `.tar.gz`, `.tgz`
- **TAR with BZIP2**: `.tar.bz2`

Supports unlimited nesting depth (up to `MAX_NESTED_LEVEL` safety limit).

## Pattern Matching

Uses Python's `fnmatch` for glob-style matching:

| Pattern | Matches |
|---------|---------|
| `*.json` | JSON files in root |
| `**/*.json` | JSON files at any depth |
| `src/*.py` | Python files in `src` |
| `**/config.*` | Files named `config` with any extension |
| `**/*.txt` | All text files |

## Usage Examples

## End-to-End Workflow Example

This example demonstrates the complete workflow for extracting and retrieving results using a test archive file with deeply nested structure.

### Step 1: Submit an Extraction Job

Submit the archive file and pattern to extract:
```bash
curl.exe -X POST "http://localhost:5000/extractions" \
  -F "archive=@test_deeply_nested.zip" \
  -F "pattern=**/*.json"
```

**Response**: Returns a job ID (example: `de4e304d-72a6-470d-8210-5671dee9ba49`)

### Step 2: Check Job Status

Query the job status to monitor extraction progress:
```bash
curl.exe -X GET "http://localhost:5000/extractions/de4e304d-72a6-470d-8210-5671dee9ba49"
```

**Response**: Shows job status (`pending`, `processing`, `completed`, or `failed`), match count, and timing information.

### Step 3: Retrieve Extraction Results

Once the job is completed, fetch the matched files:
```bash
curl.exe -X GET "http://localhost:5000/extractions/de4e304d-72a6-470d-8210-5671dee9ba49/results"
```

**Response**: Returns paginated list of all matched files with metadata (path, size, nesting level, source archive).

### Extract all JSON files
```bash
curl -X POST http://localhost:5000/extractions \
  -F "pattern=**/*.json" \
  -F "archive=@project.zip"

# Returns job_id, check status with:
curl http://localhost:5000/extractions/{job_id}

# Get results when completed:
curl "http://localhost:5000/extractions/{job_id}/results"
```

### Extract Python files from nested archives
```bash
curl -X POST http://localhost:5000/extractions \
  -F "pattern=**/*.py" \
  -F "archive=@source-code.tar.gz"
```

### Extract specific pattern
```bash
curl -X POST http://localhost:5000/extractions \
  -F "pattern=src/**/config.*" \
  -F "archive=@backup.tar.bz2"
```

## Testing

```bash
# Run all tests
pytest tests/ -v
```

Test coverage includes:
- **Archive Extraction**: ZIP and TAR.GZ format extraction with file content verification
- **Nested Archives**: Multi-level archive extraction with nesting depth tracking
- **Unsupported Formats**: Error handling for unsupported archive types (e.g., RAR)
- **Resource Management**: Temporary directory cleanup and extraction state management
- **Pattern Matching**: Glob pattern matching with single and multiple file matches; no-match scenarios
- **API Validation**: Request validation for missing or empty parameters in POST /extractions
- **Job Management**: Job creation, submission, and background job triggering
- **Status Tracking**: Job status retrieval with complete metadata (timestamps, match counts, errors)
- **Result Retrieval**: Paginated result retrieval with complete response structure and field validation
- **Error Handling**: HTTP status codes for various scenarios (404 nonexistent jobs, 500 failed jobs, 202 pending jobs)
- **Job States**: Pending, processing, completed, and failed states with appropriate responses
- **End-to-End Workflow**: Full extraction workflow from submission through result retrieval
- **Health Checks**: Service and database connectivity validation

## Project Structure

```
.
├── app.py                      # Main Flask application
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Container image definition
├── docker-compose.yml          # Multi-container setup
├── tests/
│   ├── conftest.py            # Pytest configuration
│   ├── test_app.py            # Unit tests for extraction logic
│   ├── test_integration.py     # Integration tests
│   ├── test_routes.py          # API endpoint tests
│   └── __pycache__/            # Pytest cache
└── README.md                   # This file
└── test_deeply_nested.zip      # Sample Archive
```

## Database Schema

Automatically created on startup (PostgreSQL):

```sql
CREATE TABLE jobs (
  id VARCHAR(36) PRIMARY KEY,
  status VARCHAR(20) DEFAULT 'pending',
  pattern VARCHAR(255) NOT NULL,
  archive_name VARCHAR(255) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  completed_at TIMESTAMP,
  error TEXT,
  matches INTEGER DEFAULT 0
);

CREATE TABLE results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id VARCHAR(36) REFERENCES jobs(id) ON DELETE CASCADE,
  file_path VARCHAR(1024) NOT NULL,
  file_name VARCHAR(255) NOT NULL,
  file_size INTEGER NOT NULL,
  nesting_level INTEGER NOT NULL,
  source_archive VARCHAR(255) NOT NULL,
  extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Development

### Key Classes

**ArchiveExtractor**: Core extraction engine
- `extract_archive(archive_path)`: Extract archive to temporary directory
- `matches_pattern(file_path, pattern)`: Glob pattern matching
- `process_archive_task()`: Parallel extraction task
- `run(archive_path, pattern)`: Start root extraction

**Job Model**: Extraction job in database
- Status: `pending`, `processing`, `completed`, `failed`

**Result Model**: Matched file in database
- Stores file metadata with pagination support

### Running Locally

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Set environment variables and start
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=extractor
export DB_USER=postgres
export DB_PASSWORD=password
export PORT=5000

python app.py
```
