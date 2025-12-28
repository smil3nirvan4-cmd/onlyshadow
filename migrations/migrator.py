"""
S.S.I. SHADOW - Database Migration System for BigQuery
Manages schema versions and migrations for BigQuery datasets.
"""

import os
import re
import logging
import hashlib
import importlib.util
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import json

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class MigrationConfig:
    """Configuration for migration system."""
    
    # BigQuery settings
    project_id: str
    dataset_id: str
    location: str = "US"
    
    # Migration settings
    migrations_dir: str = "migrations/versions"
    migrations_table: str = "_migrations"
    
    # Behavior
    dry_run: bool = False
    allow_destructive: bool = False
    lock_timeout_seconds: int = 300
    
    @classmethod
    def from_env(cls) -> 'MigrationConfig':
        """Create config from environment variables."""
        return cls(
            project_id=os.getenv("GCP_PROJECT_ID", ""),
            dataset_id=os.getenv("BQ_DATASET", "ssi_shadow"),
            location=os.getenv("BQ_LOCATION", "US"),
            migrations_dir=os.getenv("MIGRATIONS_DIR", "migrations/versions"),
            dry_run=os.getenv("MIGRATIONS_DRY_RUN", "false").lower() == "true",
            allow_destructive=os.getenv("MIGRATIONS_ALLOW_DESTRUCTIVE", "false").lower() == "true"
        )


# =============================================================================
# MIGRATION TYPES
# =============================================================================

class MigrationDirection(Enum):
    """Direction of migration."""
    UP = "up"
    DOWN = "down"


class MigrationStatus(Enum):
    """Status of a migration."""
    PENDING = "pending"
    APPLIED = "applied"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class Migration:
    """Represents a database migration."""
    
    version: str
    name: str
    description: str
    up_sql: str
    down_sql: Optional[str] = None
    checksum: Optional[str] = None
    applied_at: Optional[datetime] = None
    status: MigrationStatus = MigrationStatus.PENDING
    execution_time_ms: Optional[int] = None
    
    def __post_init__(self):
        if self.checksum is None:
            self.checksum = self._calculate_checksum()
    
    def _calculate_checksum(self) -> str:
        """Calculate checksum of migration SQL."""
        content = f"{self.up_sql}:{self.down_sql or ''}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    @property
    def id(self) -> str:
        """Get migration ID (version_name)."""
        return f"{self.version}_{self.name}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "checksum": self.checksum,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "status": self.status.value,
            "execution_time_ms": self.execution_time_ms
        }


@dataclass
class MigrationResult:
    """Result of a migration operation."""
    
    migration: Migration
    direction: MigrationDirection
    success: bool
    started_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    statements_executed: int = 0
    dry_run: bool = False
    
    @property
    def duration_ms(self) -> Optional[int]:
        """Get duration in milliseconds."""
        if self.completed_at is None:
            return None
        return int((self.completed_at - self.started_at).total_seconds() * 1000)


# =============================================================================
# MIGRATION FILE PARSER
# =============================================================================

class MigrationParser:
    """Parses migration files in various formats."""
    
    # Pattern for migration file names: 001_create_users_table.sql
    FILENAME_PATTERN = re.compile(r'^(\d{3,})_([a-z0-9_]+)\.(sql|py)$')
    
    # SQL comment patterns for metadata
    DESCRIPTION_PATTERN = re.compile(r'--\s*description:\s*(.+)', re.IGNORECASE)
    UP_SECTION_PATTERN = re.compile(r'--\s*\+migrate\s+up', re.IGNORECASE)
    DOWN_SECTION_PATTERN = re.compile(r'--\s*\+migrate\s+down', re.IGNORECASE)
    
    @classmethod
    def parse_filename(cls, filename: str) -> Optional[Tuple[str, str]]:
        """
        Parse migration filename to extract version and name.
        
        Args:
            filename: Migration filename
        
        Returns:
            Tuple of (version, name) or None if invalid
        """
        match = cls.FILENAME_PATTERN.match(filename)
        if match:
            return match.group(1), match.group(2)
        return None
    
    @classmethod
    def parse_sql_file(cls, content: str) -> Tuple[str, str, Optional[str]]:
        """
        Parse SQL migration file content.
        
        Format:
            -- description: Create users table
            -- +migrate up
            CREATE TABLE users (...);
            
            -- +migrate down
            DROP TABLE users;
        
        Args:
            content: File content
        
        Returns:
            Tuple of (description, up_sql, down_sql)
        """
        # Extract description
        desc_match = cls.DESCRIPTION_PATTERN.search(content)
        description = desc_match.group(1).strip() if desc_match else "No description"
        
        # Split into up and down sections
        up_match = cls.UP_SECTION_PATTERN.search(content)
        down_match = cls.DOWN_SECTION_PATTERN.search(content)
        
        if up_match:
            start = up_match.end()
            end = down_match.start() if down_match else len(content)
            up_sql = content[start:end].strip()
        else:
            # If no markers, treat entire content as up migration
            up_sql = content.strip()
        
        down_sql = None
        if down_match:
            down_sql = content[down_match.end():].strip()
        
        return description, up_sql, down_sql
    
    @classmethod
    def load_migration(cls, filepath: Path) -> Optional[Migration]:
        """
        Load a migration from a file.
        
        Args:
            filepath: Path to migration file
        
        Returns:
            Migration object or None if invalid
        """
        parsed = cls.parse_filename(filepath.name)
        if not parsed:
            logger.warning(f"Invalid migration filename: {filepath.name}")
            return None
        
        version, name = parsed
        
        if filepath.suffix == '.sql':
            content = filepath.read_text()
            description, up_sql, down_sql = cls.parse_sql_file(content)
            
            return Migration(
                version=version,
                name=name,
                description=description,
                up_sql=up_sql,
                down_sql=down_sql
            )
        
        elif filepath.suffix == '.py':
            # Load Python migration module
            spec = importlib.util.spec_from_file_location(f"migration_{version}", filepath)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            return Migration(
                version=version,
                name=name,
                description=getattr(module, 'DESCRIPTION', 'No description'),
                up_sql=getattr(module, 'UP_SQL', ''),
                down_sql=getattr(module, 'DOWN_SQL', None)
            )
        
        return None


# =============================================================================
# BIGQUERY MIGRATOR
# =============================================================================

class BigQueryMigrator:
    """
    Database migration manager for BigQuery.
    
    Features:
    - Version tracking in _migrations table
    - Up and down migrations
    - Dry run mode
    - Checksum verification
    - Transaction-like behavior (best effort)
    """
    
    def __init__(self, config: MigrationConfig):
        """
        Initialize BigQuery migrator.
        
        Args:
            config: Migration configuration
        """
        self.config = config
        self._client = None
        self._migrations_dir = Path(config.migrations_dir)
    
    @property
    def client(self):
        """Lazy-load BigQuery client."""
        if self._client is None:
            try:
                from google.cloud import bigquery
                self._client = bigquery.Client(
                    project=self.config.project_id,
                    location=self.config.location
                )
            except ImportError:
                raise ImportError(
                    "google-cloud-bigquery is required. "
                    "Install with: pip install google-cloud-bigquery"
                )
        return self._client
    
    @property
    def dataset_ref(self) -> str:
        """Get full dataset reference."""
        return f"{self.config.project_id}.{self.config.dataset_id}"
    
    @property
    def migrations_table_ref(self) -> str:
        """Get full migrations table reference."""
        return f"{self.dataset_ref}.{self.config.migrations_table}"
    
    async def initialize(self):
        """Initialize migrations table if it doesn't exist."""
        create_sql = f"""
        CREATE TABLE IF NOT EXISTS `{self.migrations_table_ref}` (
            version STRING NOT NULL,
            name STRING NOT NULL,
            description STRING,
            checksum STRING NOT NULL,
            applied_at TIMESTAMP NOT NULL,
            status STRING NOT NULL,
            execution_time_ms INT64,
            
            PRIMARY KEY (version) NOT ENFORCED
        )
        OPTIONS(
            description='Migration history tracking table'
        )
        """
        
        if not self.config.dry_run:
            self._execute_sql(create_sql)
            logger.info("Migrations table initialized")
        else:
            logger.info(f"[DRY RUN] Would create migrations table:\n{create_sql}")
    
    def _execute_sql(self, sql: str) -> Any:
        """Execute SQL statement."""
        job = self.client.query(sql)
        return job.result()
    
    def _get_applied_migrations(self) -> Dict[str, Dict[str, Any]]:
        """Get all applied migrations from tracking table."""
        try:
            query = f"""
            SELECT version, name, checksum, applied_at, status, execution_time_ms
            FROM `{self.migrations_table_ref}`
            WHERE status = 'applied'
            ORDER BY version
            """
            
            results = {}
            for row in self._execute_sql(query):
                results[row.version] = {
                    "version": row.version,
                    "name": row.name,
                    "checksum": row.checksum,
                    "applied_at": row.applied_at,
                    "status": row.status,
                    "execution_time_ms": row.execution_time_ms
                }
            
            return results
        except Exception as e:
            # Table might not exist yet
            logger.debug(f"Could not read migrations table: {e}")
            return {}
    
    def _load_migrations(self) -> List[Migration]:
        """Load all migration files from directory."""
        if not self._migrations_dir.exists():
            logger.warning(f"Migrations directory not found: {self._migrations_dir}")
            return []
        
        migrations = []
        for filepath in sorted(self._migrations_dir.glob("*")):
            if filepath.suffix in ['.sql', '.py']:
                migration = MigrationParser.load_migration(filepath)
                if migration:
                    migrations.append(migration)
        
        return migrations
    
    def _record_migration(
        self,
        migration: Migration,
        status: MigrationStatus,
        execution_time_ms: int
    ):
        """Record migration in tracking table."""
        insert_sql = f"""
        INSERT INTO `{self.migrations_table_ref}` 
        (version, name, description, checksum, applied_at, status, execution_time_ms)
        VALUES (
            '{migration.version}',
            '{migration.name}',
            '{migration.description.replace("'", "''")}',
            '{migration.checksum}',
            CURRENT_TIMESTAMP(),
            '{status.value}',
            {execution_time_ms}
        )
        """
        
        self._execute_sql(insert_sql)
    
    def _remove_migration_record(self, version: str):
        """Remove migration record from tracking table."""
        delete_sql = f"""
        DELETE FROM `{self.migrations_table_ref}`
        WHERE version = '{version}'
        """
        
        self._execute_sql(delete_sql)
    
    async def get_pending_migrations(self) -> List[Migration]:
        """
        Get list of pending migrations.
        
        Returns:
            List of migrations not yet applied
        """
        applied = self._get_applied_migrations()
        all_migrations = self._load_migrations()
        
        pending = []
        for migration in all_migrations:
            if migration.version not in applied:
                migration.status = MigrationStatus.PENDING
                pending.append(migration)
            else:
                # Verify checksum
                applied_data = applied[migration.version]
                if applied_data["checksum"] != migration.checksum:
                    logger.warning(
                        f"Checksum mismatch for migration {migration.version}: "
                        f"file={migration.checksum}, db={applied_data['checksum']}"
                    )
        
        return pending
    
    async def get_applied_migrations(self) -> List[Migration]:
        """
        Get list of applied migrations.
        
        Returns:
            List of applied migrations
        """
        applied_data = self._get_applied_migrations()
        all_migrations = self._load_migrations()
        
        applied = []
        for migration in all_migrations:
            if migration.version in applied_data:
                data = applied_data[migration.version]
                migration.status = MigrationStatus.APPLIED
                migration.applied_at = data["applied_at"]
                migration.execution_time_ms = data["execution_time_ms"]
                applied.append(migration)
        
        return applied
    
    async def migrate(
        self,
        target_version: Optional[str] = None
    ) -> List[MigrationResult]:
        """
        Run pending migrations.
        
        Args:
            target_version: Optional target version to migrate to
        
        Returns:
            List of migration results
        """
        await self.initialize()
        
        pending = await self.get_pending_migrations()
        
        if target_version:
            pending = [m for m in pending if m.version <= target_version]
        
        if not pending:
            logger.info("No pending migrations")
            return []
        
        results = []
        for migration in pending:
            result = await self._apply_migration(migration)
            results.append(result)
            
            if not result.success:
                logger.error(f"Migration {migration.version} failed, stopping")
                break
        
        return results
    
    async def _apply_migration(self, migration: Migration) -> MigrationResult:
        """Apply a single migration."""
        logger.info(f"Applying migration {migration.version}: {migration.name}")
        
        result = MigrationResult(
            migration=migration,
            direction=MigrationDirection.UP,
            success=False,
            started_at=datetime.utcnow(),
            dry_run=self.config.dry_run
        )
        
        try:
            # Split into statements
            statements = self._split_statements(migration.up_sql)
            
            for i, stmt in enumerate(statements):
                if self.config.dry_run:
                    logger.info(f"[DRY RUN] Would execute:\n{stmt[:200]}...")
                else:
                    self._execute_sql(stmt)
                result.statements_executed = i + 1
            
            result.success = True
            result.completed_at = datetime.utcnow()
            
            # Record migration
            if not self.config.dry_run:
                self._record_migration(
                    migration,
                    MigrationStatus.APPLIED,
                    result.duration_ms or 0
                )
            
            logger.info(
                f"Migration {migration.version} applied successfully "
                f"({result.statements_executed} statements, {result.duration_ms}ms)"
            )
        
        except Exception as e:
            result.error = str(e)
            result.completed_at = datetime.utcnow()
            logger.error(f"Migration {migration.version} failed: {e}")
            
            if not self.config.dry_run:
                self._record_migration(
                    migration,
                    MigrationStatus.FAILED,
                    result.duration_ms or 0
                )
        
        return result
    
    async def rollback(
        self,
        steps: int = 1
    ) -> List[MigrationResult]:
        """
        Rollback applied migrations.
        
        Args:
            steps: Number of migrations to rollback
        
        Returns:
            List of migration results
        """
        applied = await self.get_applied_migrations()
        
        if not applied:
            logger.info("No migrations to rollback")
            return []
        
        # Get last N migrations
        to_rollback = list(reversed(applied))[:steps]
        
        results = []
        for migration in to_rollback:
            result = await self._rollback_migration(migration)
            results.append(result)
            
            if not result.success:
                logger.error(f"Rollback of {migration.version} failed, stopping")
                break
        
        return results
    
    async def _rollback_migration(self, migration: Migration) -> MigrationResult:
        """Rollback a single migration."""
        if not migration.down_sql:
            logger.warning(f"No down migration for {migration.version}")
            return MigrationResult(
                migration=migration,
                direction=MigrationDirection.DOWN,
                success=False,
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                error="No down migration defined"
            )
        
        if not self.config.allow_destructive and self._is_destructive(migration.down_sql):
            return MigrationResult(
                migration=migration,
                direction=MigrationDirection.DOWN,
                success=False,
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                error="Destructive migration blocked. Set allow_destructive=True to proceed."
            )
        
        logger.info(f"Rolling back migration {migration.version}: {migration.name}")
        
        result = MigrationResult(
            migration=migration,
            direction=MigrationDirection.DOWN,
            success=False,
            started_at=datetime.utcnow(),
            dry_run=self.config.dry_run
        )
        
        try:
            statements = self._split_statements(migration.down_sql)
            
            for i, stmt in enumerate(statements):
                if self.config.dry_run:
                    logger.info(f"[DRY RUN] Would execute:\n{stmt[:200]}...")
                else:
                    self._execute_sql(stmt)
                result.statements_executed = i + 1
            
            result.success = True
            result.completed_at = datetime.utcnow()
            
            # Remove migration record
            if not self.config.dry_run:
                self._remove_migration_record(migration.version)
            
            logger.info(f"Migration {migration.version} rolled back successfully")
        
        except Exception as e:
            result.error = str(e)
            result.completed_at = datetime.utcnow()
            logger.error(f"Rollback of {migration.version} failed: {e}")
        
        return result
    
    def _split_statements(self, sql: str) -> List[str]:
        """Split SQL into individual statements."""
        # Simple split by semicolon (doesn't handle all edge cases)
        statements = []
        current = []
        
        for line in sql.split('\n'):
            stripped = line.strip()
            
            # Skip comments and empty lines
            if stripped.startswith('--') or not stripped:
                continue
            
            current.append(line)
            
            if stripped.endswith(';'):
                stmt = '\n'.join(current).strip()
                if stmt:
                    statements.append(stmt)
                current = []
        
        # Handle last statement without semicolon
        if current:
            stmt = '\n'.join(current).strip()
            if stmt:
                statements.append(stmt)
        
        return statements
    
    def _is_destructive(self, sql: str) -> bool:
        """Check if SQL contains destructive operations."""
        destructive_patterns = [
            r'\bDROP\s+TABLE\b',
            r'\bDROP\s+SCHEMA\b',
            r'\bDROP\s+DATABASE\b',
            r'\bTRUNCATE\b',
            r'\bDELETE\s+FROM\b',
        ]
        
        sql_upper = sql.upper()
        for pattern in destructive_patterns:
            if re.search(pattern, sql_upper):
                return True
        
        return False
    
    async def status(self) -> Dict[str, Any]:
        """
        Get migration status.
        
        Returns:
            Status dictionary
        """
        await self.initialize()
        
        applied = await self.get_applied_migrations()
        pending = await self.get_pending_migrations()
        
        return {
            "current_version": applied[-1].version if applied else None,
            "applied_count": len(applied),
            "pending_count": len(pending),
            "applied": [m.to_dict() for m in applied],
            "pending": [m.to_dict() for m in pending]
        }


# =============================================================================
# CLI COMMANDS
# =============================================================================

async def migrate_command(
    config: Optional[MigrationConfig] = None,
    target: Optional[str] = None,
    dry_run: bool = False
):
    """CLI command to run migrations."""
    if config is None:
        config = MigrationConfig.from_env()
    
    config.dry_run = dry_run
    
    migrator = BigQueryMigrator(config)
    results = await migrator.migrate(target)
    
    success_count = sum(1 for r in results if r.success)
    failed_count = len(results) - success_count
    
    print(f"\nMigrations completed: {success_count} succeeded, {failed_count} failed")
    
    return results


async def rollback_command(
    config: Optional[MigrationConfig] = None,
    steps: int = 1,
    dry_run: bool = False
):
    """CLI command to rollback migrations."""
    if config is None:
        config = MigrationConfig.from_env()
    
    config.dry_run = dry_run
    
    migrator = BigQueryMigrator(config)
    results = await migrator.rollback(steps)
    
    success_count = sum(1 for r in results if r.success)
    print(f"\nRollbacks completed: {success_count} succeeded")
    
    return results


async def status_command(config: Optional[MigrationConfig] = None):
    """CLI command to show migration status."""
    if config is None:
        config = MigrationConfig.from_env()
    
    migrator = BigQueryMigrator(config)
    status = await migrator.status()
    
    print(f"\nCurrent version: {status['current_version'] or 'None'}")
    print(f"Applied migrations: {status['applied_count']}")
    print(f"Pending migrations: {status['pending_count']}")
    
    if status['pending']:
        print("\nPending:")
        for m in status['pending']:
            print(f"  {m['version']} - {m['name']}: {m['description']}")
    
    return status


# =============================================================================
# MIGRATION GENERATOR
# =============================================================================

def generate_migration(
    name: str,
    description: str = "",
    migrations_dir: str = "migrations/versions"
) -> Path:
    """
    Generate a new migration file.
    
    Args:
        name: Migration name (will be converted to snake_case)
        description: Migration description
        migrations_dir: Directory for migration files
    
    Returns:
        Path to created migration file
    """
    # Convert name to snake_case
    name_clean = re.sub(r'[^a-zA-Z0-9]', '_', name.lower())
    name_clean = re.sub(r'_+', '_', name_clean).strip('_')
    
    # Get next version number
    migrations_path = Path(migrations_dir)
    migrations_path.mkdir(parents=True, exist_ok=True)
    
    existing = list(migrations_path.glob("*.sql"))
    if existing:
        versions = [
            int(MigrationParser.parse_filename(f.name)[0])
            for f in existing
            if MigrationParser.parse_filename(f.name)
        ]
        next_version = max(versions) + 1 if versions else 1
    else:
        next_version = 1
    
    # Generate filename
    filename = f"{next_version:03d}_{name_clean}.sql"
    filepath = migrations_path / filename
    
    # Generate content
    content = f"""-- description: {description or name}
-- +migrate up

-- Add your UP migration SQL here


-- +migrate down

-- Add your DOWN migration SQL here (optional)

"""
    
    filepath.write_text(content)
    logger.info(f"Created migration: {filepath}")
    
    return filepath
