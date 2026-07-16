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
        decision_state TEXT,
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
    CREATE TABLE IF NOT EXISTS media_analysis_runs (
        analysis_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        asset_id TEXT NOT NULL,
        idempotency_key TEXT NOT NULL UNIQUE,
        cache_key TEXT NOT NULL,
        status TEXT NOT NULL,
        attempt INTEGER NOT NULL DEFAULT 0,
        progress_percent INTEGER NOT NULL DEFAULT 0,
        error_code TEXT,
        error_message TEXT,
        next_retry_at TEXT,
        cancel_requested INTEGER NOT NULL DEFAULT 0,
        result_json TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS media_analysis_cache (
        cache_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, asset_id TEXT NOT NULL,
        source_sha256 TEXT NOT NULL, cache_key TEXT NOT NULL, state TEXT NOT NULL,
        tags_stale INTEGER NOT NULL DEFAULT 0, embedding_stale INTEGER NOT NULL DEFAULT 0,
        preview_stale INTEGER NOT NULL DEFAULT 0, proposal_index_stale INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL, stale_at TEXT,
        UNIQUE(project_id, asset_id, source_sha256, cache_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS media_scene_windows (
        scene_window_id TEXT PRIMARY KEY,
        analysis_id TEXT NOT NULL,
        source_sha256 TEXT NOT NULL,
        profile_hash TEXT NOT NULL,
        start_sec REAL NOT NULL,
        end_sec REAL NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS media_embeddings (
        embedding_id TEXT PRIMARY KEY,
        analysis_id TEXT NOT NULL,
        source_sha256 TEXT NOT NULL,
        profile_hash TEXT NOT NULL,
        embedding_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS media_analysis_profiles (
        analysis_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        profile_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS provider_trace_failed_runs (
        job_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        job_type TEXT NOT NULL,
        source_job_id TEXT,
        artifact_id TEXT,
        timeline_id TEXT,
        error_message TEXT,
        provider_trace_json TEXT,
        created_at TEXT NOT NULL,
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
    CREATE TABLE IF NOT EXISTS editing_sessions (
        session_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        timeline_id TEXT NOT NULL,
        file_uri TEXT NOT NULL,
        summary_json TEXT NOT NULL,
        session_revision INTEGER NOT NULL DEFAULT 1,
        session_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS director_proposals (
        proposal_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, status TEXT NOT NULL,
        source_session_id TEXT NOT NULL, source_script_segment_ids_json TEXT NOT NULL,
        proposal_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS director_preferences (
        project_id TEXT PRIMARY KEY, preferences_json TEXT NOT NULL, updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS project_media_library_preferences (
        project_id TEXT PRIMARY KEY, preferences_json TEXT NOT NULL, updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS director_asset_index_revisions (
        project_id TEXT PRIMARY KEY, revision INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS director_proposal_revisions (
        project_id TEXT PRIMARY KEY, revision INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS director_proposal_lifecycle_events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT, proposal_id TEXT NOT NULL,
        status TEXT NOT NULL, reason TEXT, changed_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS director_conversations (
        conversation_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS director_messages (
        message_id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL,
        text TEXT NOT NULL,
        proposal_id TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        client_message_id TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(conversation_id, client_message_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS director_message_claims (
        conversation_id TEXT NOT NULL,
        client_message_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        user_text TEXT NOT NULL,
        created_at TEXT NOT NULL,
        owner_token TEXT NOT NULL DEFAULT '', heartbeat_at TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (conversation_id, client_message_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS review_approvals (
        timeline_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        status TEXT NOT NULL,
        approved_at TEXT,
        updated_at TEXT NOT NULL,
        source_session_revision INTEGER, is_current INTEGER NOT NULL DEFAULT 1,
        invalidated_at TEXT, invalidated_reason TEXT
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
        created_at TEXT NOT NULL,
        source_session_revision INTEGER, is_current INTEGER NOT NULL DEFAULT 1,
        invalidated_at TEXT, invalidated_reason TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS subtitle_renders (
        subtitle_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        timeline_id TEXT NOT NULL,
        format TEXT NOT NULL,
        file_uri TEXT NOT NULL,
        status TEXT NOT NULL,
        summary_json TEXT,
        created_at TEXT NOT NULL,
        source_session_revision INTEGER, is_current INTEGER NOT NULL DEFAULT 1,
        invalidated_at TEXT, invalidated_reason TEXT
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
        created_at TEXT NOT NULL,
        source_session_revision INTEGER, is_current INTEGER NOT NULL DEFAULT 1,
        invalidated_at TEXT, invalidated_reason TEXT
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
    """
    CREATE TABLE IF NOT EXISTS tts_candidates (
        candidate_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        segment_id TEXT NOT NULL,
        asset_id TEXT NOT NULL,
        source_text TEXT NOT NULL,
        technical_status TEXT NOT NULL DEFAULT 'legacy_unverified',
        operator_review_status TEXT NOT NULL DEFAULT 'pending',
        target_duration_sec REAL,
        actual_duration_sec REAL,
        failure_code TEXT,
        created_at TEXT NOT NULL,
        source_session_revision INTEGER, is_current INTEGER NOT NULL DEFAULT 1,
        invalidated_at TEXT, invalidated_reason TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gemini_provider_keys (
        key_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        label TEXT NOT NULL,
        api_key_secret TEXT NOT NULL,
        primary_model TEXT NOT NULL,
        cheap_model TEXT NOT NULL,
        high_quality_model TEXT NOT NULL,
        status TEXT NOT NULL,
        cooldown_until TEXT,
        consecutive_failures INTEGER NOT NULL,
        last_error TEXT,
        last_used_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
)
