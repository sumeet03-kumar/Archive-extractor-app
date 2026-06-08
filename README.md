# Archive File Extractor Service

A robust, production-grade HTTP service for extracting and searching files within archive files (zip, tar, tar.gz, tar.bz2) and nested archives at any depth. Results are persisted to a PostgreSQL database with full audit trails and accessible via a comprehensive REST API.

## Features

- **Nested Archive Support**: Recursively extracts and searches through archives nested at any depth (with configurable safety limits, default: 10 levels)
- **Parallel Processing**: Multi-threaded concurrent extraction of nested archives using a shared ThreadPoolExecutor for optimal CPU utilization
- **Memory Efficient**: Producer-Consumer pattern with queue-based streaming and batch commits (100 results per commit) to maintain constant memory usage
- **Pattern Matching**: Glob-style pattern matching for flexible file filtering (e.g., `**/*.json`, `src/**/config.*`)
- **Asynchronous Job Processing**: Non-blocking job submission with background worker pool for handling multiple simultaneous extractions
- **Database Persistence**: Results stored in PostgreSQL with comprehensive metadata (file path, size, nesting level, source archive, extraction timestamp)
- **RESTful API**: Full-featured HTTP API for job submission, status tracking, paginated result retrieval, and health checks
- **Docker Containerization**: Complete Docker setup with docker-compose for easy single-command deployment
- **Comprehensive Logging**: Structured logging with job tracking, depth indicators, and detailed error messages for debugging and auditing
- **Error Handling**: Graceful error handling with informative error messages, automatic cleanup on failure, and proper resource management
- **Archive Format Support**: Handles zip, tar, tar.gz (tgz), and tar.bz2 formats seamlessly
- **Security**: Safe extraction with protection against path traversal attacks (Zip Slip) and symlink escapes

## Architecture

### Core Components

1. **Flask Application**: Lightweight HTTP service handling REST API endpoints
2. **SQLAlchemy ORM**: Database abstraction layer for PostgreSQL
3. **ArchiveExtractor**: Core extraction engine with nested archive support
4. **ThreadPoolExecutor**: Separate thread pools for job processing and extraction tasks
5. **Queue-based Processing**: Producer-Consumer pattern for memory-efficient result streaming

### Database Models

1. **Job**: Tracks extraction jobs with status, pattern, archive name, timestamps, and error information
2. **Result**: Stores individual file matches with full metadata (path, size, nesting level, source archive)

### Design Decisions

1. **Framework**: Flask is used for its simplicity, lightweight nature, and flexibility in building HTTP services without unnecessary overhead
2. **Database**: PostgreSQL provides robust ACID compliance, reliable transaction management, and excellent support for concurrent access
3. **Concurrency Model**: 
   - **Dual ThreadPoolExecutor**: Separate executors for job management and extraction tasks
   - **Task Tracking**: Thread-safe synchronization with Condition variables ensures proper coordination
   - **Event-based Coordination**: Threading.Condition ensures the consumer waits for all parallel tasks to complete
4. **Memory Management**: 
   - **Producer-Consumer Queue**: Extraction tasks immediately push matches to a queue
   - **Batch Commits**: Database commits occur every 100 results to balance throughput and memory usage
   - **Streaming Processing**: Results are not accumulated in memory; they flow directly to the database
5. **File Upload**: Multipart form-data upload for direct archive files (allows validation before processing and immediate server-side control)
6. **Nesting Limit**: Configurable maximum nesting depth (default: 10) prevents stack overflow, infinite loops, and resource exhaustion from malicious or corrupted archives
7. **Security**: Safe extraction with path traversal validation for both ZIP and TAR archives

### Performance Optimizations

1. **Parallel Nested Extraction**: When a nested archive is discovered, a new task is submitted to the executor instead of blocking, allowing multiple archives to be processed simultaneously across CPU cores
2. **Queue-based Streaming**: Matches flow from extraction tasks directly to the database queue without intermediate storage
3. **Batch Database Commits**: Committing every 100 results instead of per-result dramatically improves database throughput while maintaining low memory pressure
4. **Temporary Directory Management**: Archives are extracted to isolated temporary directories and cleaned up immediately after processing
5. **Efficient Archive Detection**: Case-insensitive extension checking for quick archive format identification

## Prerequisites

- Python 3.11+
- PostgreSQL 15+ (or use Docker Compose)
- pip or poetry for dependency management

## Installation

### Option 1: Local Setup with PostgreSQL

1. **Clone or navigate to the project**:
```bash
cd d:\lgsi-interview
```

2. **Create and activate a virtual environment**:
```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

3. **Install dependencies**:
```bash
pip install -r requirements.txt
```

4. **Set up environment variables** (create a `.env` file or set them):
```bash
DB_HOST=localhost
DB_PORT=5432
DB_NAME=extractor
DB_USER=postgres
DB_PASSWORD=password
PORT=5000
JOB_CONCURRENCY=4
EXTRACTION_CONCURRENCY=8
MAX_NESTED_LEVEL=10
```

5. **Ensure PostgreSQL is running** and create the database:
```bash
createdb -U postgres extractor
```

### Option 2: Docker Compose (Recommended)

1. **Build and start the service**:
```bash
docker-compose up --build
```

This will:
- Create and start a PostgreSQL 15 container
- Build the Flask application image
- Set up networking between services
- Initialize the database with health checks

The service will be available at `http://localhost:5000`

## Running the Application

### Local Development
```bash
python app.py
```

The service will start on `http://localhost:5000`

### With Docker
```bash
docker-compose up
```

## API Endpoints

### 1. Submit Extraction Job

**Endpoint**: `POST /extractions`

Submit an archive file and pattern to extract matching files.

**Parameters**:
- `pattern` (form data): Glob pattern for file matching (e.g., `*.txt`, `**/*.json`, `src/**/config.*`)
- `archive` (form file): The archive file to process (zip, tar, tar.gz, tar.bz2)

**Response**: 
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending"
}
```

**Example**:
```bash
curl -X POST http://localhost:5000/extractions \
  -F "pattern=*.txt" \
  -F "archive=@myarchive.zip"
```

### 2. Get Job Status

**Endpoint**: `GET /extractions/<job_id>`

Retrieve the status and metadata of an extraction job.

**Response**:
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

**Status values**: `pending`, `processing`, `completed`, `failed`

**Example**:
```bash
curl http://localhost:5000/extractions/550e8400-e29b-41d4-a716-446655440000
```

### 3. Get Extraction Results (Paginated)

**Endpoint**: `GET /extractions/<job_id>/results?page=1&per_page=20`

Retrieve paginated results from a completed extraction job.

**Query Parameters**:
- `page` (optional): Page number (default: 1)
- `per_page` (optional): Results per page (default: 20)

**Response**:
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
      "job_id": "550e8400-e29b-41d4-a716-446655440000",
      "file_path": "config.txt",
      "file_name": "config.txt",
      "file_size": 1024,
      "nesting_level": 0,
      "source_archive": "myarchive.zip",
      "extracted_at": "2024-01-15T10:35:00"
    },
    {
      "id": 2,
      "job_id": "550e8400-e29b-41d4-a716-446655440000",
      "file_path": "nested/readme.txt",
      "file_name": "readme.txt",
      "file_size": 2048,
      "nesting_level": 1,
      "source_archive": "inner_archive.zip",
      "extracted_at": "2024-01-15T10:35:01"
    }
  ]
}
```

**Example**:
```bash
curl "http://localhost:5000/extractions/550e8400-e29b-41d4-a716-446655440000/results?page=1&per_page=20"
```

## Configuration

Environment variables for customization:

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | localhost | PostgreSQL host |
| `DB_PORT` | 5432 | PostgreSQL port |
| `DB_NAME` | extractor | Database name |
| `DB_USER` | postgres | Database user |
| `DB_PASSWORD` | password | Database password |
| `PORT` | 5000 | Service port |
| `JOB_CONCURRENCY` | 4 | Number of concurrent job workers |
| `EXTRACTION_CONCURRENCY` | 8 | Number of concurrent extraction workers |
| `MAX_NESTED_LEVEL` | 10 | Maximum archive nesting depth (prevents infinite recursion) |

## Testing

Run the test suite:

```bash
pytest tests/ -v
```

Test coverage includes:
- Archive type detection (zip, tar, tar.gz, tar.bz2)
- Pattern matching with glob patterns
- ZIP archive extraction and nested extraction
- Resource cleanup and temporary directory handling

**Run specific test**:
```bash
pytest tests/test_app.py::test_extract_and_find_zip -v
```

## Usage Examples

### Example 1: Extract all JSON files from an archive

```bash
# Submit the job
curl -X POST http://localhost:5000/extractions \
  -F "pattern=**/*.json" \
  -F "archive=@project.zip"

# Response:
# {"job_id": "abc-123-def", "status": "pending"}

# Check status
curl http://localhost:5000/extractions/abc-123-def

# Get results (when completed)
curl "http://localhost:5000/extractions/abc-123-def/results?page=1&per_page=50"
```

### Example 2: Extract Python files from nested archives

```bash
curl -X POST http://localhost:5000/extractions \
  -F "pattern=**/*.py" \
  -F "archive=@source-code.tar.gz"
```

### Example 3: Extract specific files matching a pattern

```bash
curl -X POST http://localhost:5000/extractions \
  -F "pattern=src/**/config.*" \
  -F "archive=@backup.tar.bz2"
```

## Project Structure

```
.
├── app.py                      # Main Flask application
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Container image definition
├── docker-compose.yml          # Multi-container setup
├── tests/
│   ├── conftest.py            # Pytest configuration
│   └── test_app.py            # Unit and integration tests
└── README.md                   # This file
```

## Supported Archive Formats

- **ZIP**: `.zip`
- **TAR**: `.tar`
- **TAR with GZIP**: `.tar.gz`, `.tgz`
- **TAR with BZIP2**: `.tar.bz2`

## Security Considerations

1. **Path Traversal Protection**: Validates all extracted paths to prevent Zip Slip attacks
2. **Symlink Protection**: TAR extraction prevents symlink escapes
3. **Nesting Limits**: Configurable max nesting depth prevents resource exhaustion
4. **File Cleanup**: Temporary files are automatically cleaned up after processing
5. **Error Handling**: Sensitive error details are logged but not exposed to clients

## Troubleshooting

### Database Connection Error
- Ensure PostgreSQL is running and accessible
- Verify DB_HOST, DB_PORT, DB_USER, and DB_PASSWORD are correct
- Check that the database exists: `psql -U postgres -l | grep extractor`

### Archive Extraction Fails
- Verify the archive format is supported
- Check that the archive is not corrupted
- Review logs for specific error messages

### Slow Performance
- Increase `EXTRACTION_CONCURRENCY` for faster processing (requires more CPU)
- Check database performance and ensure PostgreSQL has sufficient resources
- Consider reducing `MAX_NESTED_LEVEL` if dealing with deeply nested archives

### Permission Errors
- Ensure the application has write permissions to the temp directory
- Check that PostgreSQL user has proper permissions

## Performance Notes

- Parallel extraction allows processing multiple nested archives simultaneously
- Batch database commits (every 100 results) optimize throughput
- Memory usage remains constant regardless of archive size due to streaming
- The service can handle archives ranging from MB to GB in size

## Development

### Adding Support for New Archive Formats

1. Update `SUPPORTED_EXTENSIONS` in the `ArchiveExtractor` class
2. Add extraction logic in the `extract_archive()` method
3. Add safe extraction validation similar to `_safe_extract_zip()` and `_safe_extract_tar()`
4. Add tests in `tests/test_app.py`

### Extending the API

The application uses Flask and SQLAlchemy, making it easy to:
- Add new endpoints
- Modify database schema
- Implement additional filtering or search capabilities

## Quick Start

### Prerequisites

- **Docker and Docker Compose** (recommended for easiest setup)
- **Or**: Python 3.9+, PostgreSQL 12+

### Using Docker Compose (Recommended)

```bash
# Navigate to the project directory
cd lgsi-interview

# Build and start both PostgreSQL and the service
docker-compose up --build

# Service runs on http://localhost:5000
# PostgreSQL runs on localhost:5432
```

The `docker-compose.yml` automatically:
- Spins up PostgreSQL 15 with pre-configured credentials
- Builds and runs the Flask application
- Sets up all environment variables
- Manages container networking

### Manual Setup (Linux/macOS)

```bash
# Install system dependencies (Ubuntu/Debian)
sudo apt-get update && apt-get install -y postgresql-client libpq-dev

# Create a Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Ensure PostgreSQL is running, then create the database
createdb -h localhost -U postgres extractor

# Set up environment variables
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=extractor
export DB_USER=postgres
export DB_PASSWORD=password
export PORT=5000
export CONCURRENCY_REQUESTS=4
export MAX_NESTED_LEVEL=10

# Create database tables
python -c "from app import init_db; init_db()"

# Start the service
python app.py
```

### Manual Setup (Windows)

```bash
# Create a Python virtual environment
python -m venv venv
venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

# Set up environment variables (PowerShell)
$env:DB_HOST = "localhost"
$env:DB_PORT = 5432
$env:DB_NAME = "extractor"
$env:DB_USER = "postgres"
$env:DB_PASSWORD = "password"
$env:PORT = 5000
$env:CONCURRENCY_REQUESTS = 4
$env:MAX_NESTED_LEVEL = 10

# Create database tables
python -c "from app import init_db; init_db()"

# Start the service
python app.py
```

## Configuration

All configuration is done via environment variables. Set these before starting the service:

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | localhost | PostgreSQL host address |
| `DB_PORT` | 5432 | PostgreSQL port number |
| `DB_NAME` | extractor | Database name to use |
| `DB_USER` | postgres | PostgreSQL user for authentication |
| `DB_PASSWORD` | password | PostgreSQL password for authentication |
| `PORT` | 5000 | HTTP service port (Flask app listens on `0.0.0.0:{PORT}`) |
| `CONCURRENCY_REQUESTS` | 4 | Number of parallel workers in the ThreadPoolExecutor for archive extraction |
| `MAX_NESTED_LEVEL` | 10 | Maximum depth of nested archives to extract (safety limit) |

### Database Connection

The service connects to PostgreSQL using SQLAlchemy:
```
postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}
```

The connection is automatically established when the service starts, with retry logic (up to 30 attempts, 1-second delays) for resilience during container startup orchestration.

## API Reference

### 1. Health Check

**Endpoint:** `GET /health`

Check the service health and database connectivity.

**Request:**
```bash
curl -X GET http://localhost:5000/health
```

**Response (200 OK):**
```json
{
  "status": "healthy",
  "timestamp": "2026-05-25T10:30:45.123456",
  "database": "connected"
}
```

**Response (503 Service Unavailable):**
```json
{
  "status": "unhealthy",
  "timestamp": "2026-05-25T10:30:45.123456",
  "database": "disconnected",
  "error": "Connection refused"
}
```

---

### 2. Submit Extraction Job

**Endpoint:** `POST /extractions`

Submit a new archive extraction job. The archive is uploaded as multipart form-data.

**Request Headers:**
```
Content-Type: multipart/form-data
```

**Form Parameters:**
- `archive` (file, required): The archive file to extract (zip, tar, tar.gz, tar.bz2)
- `pattern` (string, required): Glob pattern for file matching (e.g., `**/*.json`, `src/**/config.*`, `*.txt`)

**Request Example:**
```bash
# Extract all JSON files from a zip
curl -X POST http://localhost:5000/extractions \
  -F "archive=@test_archive.zip" \
  -F "pattern=**/*.json"

# Extract all Python files from any directory
curl -X POST http://localhost:5000/extractions \
  -F "archive=@my_project.tar.gz" \
  -F "pattern=**/*.py"

# Extract specific files
curl -X POST http://localhost:5000/extractions \
  -F "archive=@data.zip" \
  -F "pattern=config.json"
```

**Response (202 Accepted):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Extraction job submitted",
  "timestamp": "2026-05-25T10:30:45.123456"
}
```

The service returns immediately with a `job_id`. Use this ID to track job progress and retrieve results.

**Error Responses:**
- `400 Bad Request`: Missing `pattern` or `archive` parameter
- `400 Bad Request`: No file selected for archive upload
- `500 Internal Server Error`: Failed to submit job (e.g., disk write error)

---

### 3. Get Job Status

**Endpoint:** `GET /extractions/<job_id>`

Get the current status and summary of an extraction job.

**Request:**
```bash
curl -X GET http://localhost:5000/extractions/550e8400-e29b-41d4-a716-446655440000
```

**Response (200 OK) - Pending:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "pattern": "**/*.json",
  "archive_name": "test_archive.zip",
  "created_at": "2026-05-25T10:30:45.123456",
  "completed_at": null,
  "error": null,
  "matches": 0
}
```

**Response (200 OK) - Completed:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "pattern": "**/*.json",
  "archive_name": "test_archive.zip",
  "created_at": "2026-05-25T10:30:45.123456",
  "completed_at": "2026-05-25T10:31:02.456789",
  "error": null,
  "matches": 45
}
```

**Response (200 OK) - Failed:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "failed",
  "pattern": "**/*.json",
  "archive_name": "test_archive.zip",
  "created_at": "2026-05-25T10:30:45.123456",
  "completed_at": "2026-05-25T10:30:50.987654",
  "error": "Corrupted archive: unexpected end of file",
  "matches": 0
}
```

**Job Status Values:**
- `pending`: Job created, waiting to be processed
- `processing`: Extraction is currently in progress
- `completed`: Extraction finished successfully
- `failed`: Extraction encountered an error

**Error Response:**
- `404 Not Found`: Job ID does not exist

---

### 4. Get Job Results

**Endpoint:** `GET /extractions/<job_id>/results`

Retrieve the matched files from a completed extraction job with pagination support.

**Query Parameters:**
- `page` (integer, default: 1): Page number (1-indexed)
- `per_page` (integer, default: 20, max: 100): Results per page

**Request Examples:**
```bash
# Get first page of results
curl -X GET "http://localhost:5000/extractions/550e8400-e29b-41d4-a716-446655440000/results"

# Get second page with 50 results per page
curl -X GET "http://localhost:5000/extractions/550e8400-e29b-41d4-a716-446655440000/results?page=2&per_page=50"
```

**Response (200 OK):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "total_count": 245,
  "page": 1,
  "per_page": 20,
  "total_pages": 13,
  "results": [
    {
      "id": 1,
      "job_id": "550e8400-e29b-41d4-a716-446655440000",
      "file_path": "config.json",
      "file_name": "config.json",
      "file_size": 2048,
      "nesting_level": 0,
      "source_archive": "test_archive.zip",
      "extracted_at": "2026-05-25T10:31:01.234567"
    },
    {
      "id": 2,
      "job_id": "550e8400-e29b-41d4-a716-446655440000",
      "file_path": "src/settings/app.json",
      "file_name": "app.json",
      "file_size": 512,
      "nesting_level": 0,
      "source_archive": "test_archive.zip",
      "extracted_at": "2026-05-25T10:31:01.345678"
    },
    {
      "id": 3,
      "job_id": "550e8400-e29b-41d4-a716-446655440000",
      "file_path": "data/nested_archive.tar.gz/package.json",
      "file_name": "package.json",
      "file_size": 1024,
      "nesting_level": 1,
      "source_archive": "test_archive.zip",
      "extracted_at": "2026-05-25T10:31:05.456789"
    }
  ]
}
```

**Result Field Descriptions:**
- `id`: Unique result identifier in the database
- `job_id`: Reference to the extraction job
- `file_path`: Full path to the file within the archive structure (includes nested archive names in path)
- `file_name`: Base filename (last component of file_path)
- `file_size`: File size in bytes
- `nesting_level`: Depth of nesting (0 = root archive, 1 = nested once, etc.)
- `source_archive`: The original archive filename
- `extracted_at`: When the file was extracted (database timestamp)

**Pagination Notes:**
- If `page` < 1, defaults to page 1
- If `per_page` < 1 or > 100, defaults to 20
- `total_pages` is calculated as: `ceil(total_count / per_page)`

**Error Response:**
- `404 Not Found`: Job ID does not exist


## Supported Archive Formats

The service automatically detects and handles the following archive formats:

| Format | Extensions | Status |
|--------|-----------|--------|
| ZIP | `.zip` | ✓ Supported |
| TAR | `.tar` | ✓ Supported |
| TAR with GZIP | `.tar.gz`, `.tgz` | ✓ Supported |
| TAR with BZIP2 | `.tar.bz2` | ✓ Supported |

The service supports unlimited nesting depth (up to the configured `MAX_NESTED_LEVEL` for safety). For example, you can extract a ZIP containing a TAR.GZ containing another ZIP containing a TAR file.

## Pattern Matching

The service uses Python's `fnmatch` module for glob-style pattern matching:

| Pattern | Matches |
|---------|---------|
| `*.json` | All JSON files in root of archive |
| `**/*.json` | All JSON files at any depth |
| `src/*.py` | Python files in `src` directory |
| `**/config.*` | Files named `config` with any extension at any depth |
| `**/*.txt` | All text files at any depth |
| `data/**` | All files in the `data` directory and subdirectories |

## Database Schema

The service uses two main database tables:

### Jobs Table
```sql
CREATE TABLE jobs (
  id VARCHAR(36) PRIMARY KEY,
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  pattern VARCHAR(255) NOT NULL,
  archive_name VARCHAR(255) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  completed_at TIMESTAMP,
  error TEXT,
  matches INTEGER DEFAULT 0
);
```

### Results Table
```sql
CREATE TABLE results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id VARCHAR(36) NOT NULL REFERENCES jobs(id),
  file_path VARCHAR(1024) NOT NULL,
  file_name VARCHAR(255) NOT NULL,
  file_size INTEGER NOT NULL,
  nesting_level INTEGER NOT NULL,
  source_archive VARCHAR(255) NOT NULL,
  extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Tables are automatically created when the service starts if they don't exist.

## Testing

The project includes comprehensive pytest tests covering:

- Archive format detection (ZIP, TAR, TAR.GZ)
- Pattern matching (simple and complex glob patterns)
- Archive extraction
- Nested archive extraction
- Temporary directory cleanup

### Running Tests

```bash
# Install test dependencies (included in requirements.txt)
pip install -r requirements.txt

# Run all tests
pytest tests/

# Run with verbose output
pytest tests/ -v

# Run specific test file
pytest tests/test_app.py

# Run specific test
pytest tests/test_app.py::test_is_archive_zip -v
```

All tests use fixtures to create temporary archives and clean up resources automatically.

## Error Handling

The service handles various error scenarios gracefully:

| Scenario | Response | Details |
|----------|----------|---------|
| Missing `pattern` parameter | 400 Bad Request | Error message specifies missing parameter |
| Missing `archive` file | 400 Bad Request | Error message specifies missing file |
| Empty archive filename | 400 Bad Request | No file selected |
| Corrupted archive | 500 Server Error | Error details saved to job record |
| Database connection failure | 503 Service Unavailable | Retries automatically on startup |
| Extraction timeout/hang | Job marked `failed` | Error message logged and persisted |
| Disk space exhaustion | 500 Server Error | Temporary files cleaned up automatically |

All errors are logged with timestamps, job IDs, and detailed messages for debugging.

## Performance Characteristics

### Memory Usage
- **Constant**: Thanks to the queue-based streaming architecture, memory usage remains constant regardless of archive size or match count
- **Batch commits**: Database writes occur every 100 results, preventing memory accumulation

### Processing Speed
- **Parallelism**: Nested archives are extracted in parallel using multiple worker threads
- **I/O Efficiency**: Temporary files are extracted to disk for processing (not loaded into memory)
- **Database**: Batch commits reduce database round-trips

### Scalability
- **Concurrent Jobs**: Multiple extraction jobs run in parallel within the thread pool
- **Configurable Workers**: Adjust `CONCURRENCY_REQUESTS` to match system resources
- **Job Queue**: Jobs wait for available workers without blocking the HTTP server

### Throughput Examples (Indicative)
- **Shallow archives** (few nested levels): Limited by disk I/O speed (~100-500 MB/s)
- **Deep archives** (many nested levels): Parallelism gains 2-4x speedup with 4 workers
- **Large result sets**: Batch commits maintain consistent throughput regardless of match count

## Deployment

### Docker Deployment (Recommended)

```bash
# Pull images and start
docker-compose up --build

# View logs
docker-compose logs -f app

# Stop service
docker-compose down

# Clean up volumes (removes database data)
docker-compose down -v
```

### Kubernetes Deployment

Create a Kubernetes deployment with:
- Pod for Flask application
- PostgreSQL StatefulSet for database
- Service for HTTP access
- ConfigMap for environment variables
- PersistentVolumeClaim for database storage

### Environment Variables for Production

```bash
# Use strong passwords
DB_PASSWORD=<strong-random-password>

# Scale workers for your hardware
CONCURRENCY_REQUESTS=8  # For 8-core machine

# Set appropriate port
PORT=8080

# Adjust nesting limit based on security concerns
MAX_NESTED_LEVEL=5  # More restrictive
```

## Troubleshooting

### Service won't start
- Check PostgreSQL is running and accessible: `psql -h $DB_HOST -U $DB_USER -d $DB_NAME`
- Verify environment variables are set correctly
- Check logs: `docker-compose logs app`

### Jobs stuck in `processing`
- Check for errors in logs
- Verify database connection is stable
- Check if archive is corrupted or too deeply nested

### Results not appearing
- Ensure job has `completed` status before querying results
- Check `nesting_level` is within `MAX_NESTED_LEVEL`
- Verify pattern matches files in archive (test with `**/*`)

### Out of Memory errors
- Reduce `CONCURRENCY_REQUESTS` to lower parallel task count
- Reduce `MAX_NESTED_LEVEL` for deeply nested archives
- Check system has adequate RAM

### Database connection timeouts
- Increase `DB_HOST` timeout (check PostgreSQL `connect_timeout` setting)
- Verify network connectivity between app and database containers
- Check database resource utilization

## Development

### Project Structure
```
.
├── app.py                                 # Main Flask application
├── requirements.txt                       # Python dependencies
├── Dockerfile                             # Container image definition
├── docker-compose.yml                     # Multi-container setup
├── tests/
│   ├── conftest.py                       # Pytest configuration
│   └── test_app.py                       # Test suite
└── README.md                              # This file
```

### Key Classes and Functions

**ArchiveExtractor**: Core extraction engine
- `__init__(executor, max_depth)`: Initialize with thread pool and depth limit
- `extract_archive(archive_path)`: Extract archive to temporary directory
- `matches_pattern(file_path, pattern)`: Glob pattern matching
- `process_archive_task(...)`: Parallel extraction task
- `run(archive_path, pattern, source_archive_name)`: Start root extraction
- `cleanup()`: Clean up temporary directories

**Job Model**: Represents an extraction job in the database
- Status values: `pending`, `processing`, `completed`, `failed`
- Tracks pattern, archive name, timestamps, match count, and errors

**Result Model**: Represents a matched file in the database
- Stores file metadata: path, size, nesting level, source archive
- Supports pagination via SQLAlchemy query

### Running Locally

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start PostgreSQL (or use docker-compose postgres service)
# Set environment variables
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=extractor
export DB_USER=postgres
export DB_PASSWORD=password
export CONCURRENCY_REQUESTS=4
export MAX_NESTED_LEVEL=10

# Run application
python app.py

# In another terminal, submit a test job
curl -X POST http://localhost:5000/extractions \
  -F "archive=@test_archive.zip" \
  -F "pattern=**/*.json"
```

## License

This project is provided as-is for educational and interview purposes.

## Implementation Notes

This implementation addresses key functional gaps:

1. **Nested Parallelism**: All nested archives are processed in parallel using a shared ThreadPoolExecutor, enabling true multi-core utilization
2. **Memory Efficiency**: Queue-based producer-consumer pattern streams results directly to the database with batch commits every 100 records
3. **Source Archive Tracking**: Original archive name is consistently propagated through all recursion levels and stored in every result record
