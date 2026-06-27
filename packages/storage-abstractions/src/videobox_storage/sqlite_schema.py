PROJECT_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS projects (
        project_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        status TEXT NOT NULL,
        root_storage_uri TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS assets (
        asset_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        asset_type TEXT NOT NULL,
        storage_uri TEXT NOT NULL,
        source_kind TEXT,
        mime_type TEXT,
        duration_sec REAL,
        metadata_json TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS segments (
        segment_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        start_sec REAL,
        end_sec REAL,
        text TEXT,
        source_asset_id TEXT,
        confidence REAL,
        cleanup_decision TEXT,
        review_required INTEGER,
        metadata_json TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS transcripts (
        transcript_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        source_asset_id TEXT NOT NULL,
        transcript_uri TEXT NOT NULL,
        transcript_text TEXT NOT NULL,
        provider_name TEXT NOT NULL,
        segments_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS segment_analysis_runs (
        segment_analysis_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        transcript_id TEXT NOT NULL,
        script_asset_id TEXT,
        file_uri TEXT NOT NULL,
        segments_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS recommendations (
        recommendation_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        target_segment_id TEXT,
        recommendation_type TEXT NOT NULL,
        selected_asset_id TEXT,
        score REAL,
        reason TEXT,
        auto_apply_allowed INTEGER NOT NULL,
        review_required INTEGER NOT NULL,
        payload_json TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS jobs (
        job_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        job_type TEXT NOT NULL,
        status TEXT NOT NULL,
        input_ref TEXT,
        output_ref TEXT,
        error_message TEXT,
        started_at TEXT,
        finished_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS timelines (
        timeline_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        version TEXT NOT NULL,
        output_mode TEXT NOT NULL,
        file_uri TEXT NOT NULL,
        summary_json TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS preview_renders (
        preview_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        timeline_id TEXT NOT NULL,
        file_uri TEXT NOT NULL,
        status TEXT NOT NULL,
        summary_json TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS exports (
        export_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        timeline_id TEXT NOT NULL,
        export_type TEXT NOT NULL,
        file_uri TEXT NOT NULL,
        status TEXT NOT NULL,
        metadata_json TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS voice_samples (
        voice_sample_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        asset_id TEXT NOT NULL,
        display_name TEXT NOT NULL,
        language TEXT,
        provider_name TEXT,
        consent_note TEXT,
        metadata_json TEXT,
        created_at TEXT NOT NULL
    )
    """,
)
