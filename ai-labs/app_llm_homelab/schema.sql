-- Evaluation data only. Existing incident_memory_* tables are not modified.
CREATE SCHEMA IF NOT EXISTS llm_eval;
CREATE TABLE IF NOT EXISTS llm_eval.schema_version (
    version integer PRIMARY KEY CHECK (version = 1)
);
INSERT INTO llm_eval.schema_version VALUES (1) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS llm_eval.runs (
    id uuid PRIMARY KEY,
    fingerprint text NOT NULL,
    created_at text NOT NULL,
    name text NOT NULL,
    manifest jsonb NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (fingerprint, created_at)
);
CREATE TABLE IF NOT EXISTS llm_eval.scenarios (
    run_id uuid NOT NULL REFERENCES llm_eval.runs(id),
    scenario_id text NOT NULL,
    data jsonb NOT NULL,
    PRIMARY KEY (run_id, scenario_id)
);
CREATE TABLE IF NOT EXISTS llm_eval.contexts (
    run_id uuid NOT NULL REFERENCES llm_eval.runs(id),
    context_key text NOT NULL,
    data jsonb NOT NULL,
    PRIMARY KEY (run_id, context_key)
);
CREATE TABLE IF NOT EXISTS llm_eval.calls (
    run_id uuid NOT NULL REFERENCES llm_eval.runs(id),
    call_id text NOT NULL,
    scenario_id text NOT NULL,
    context_key text,
    llm_profile text NOT NULL,
    embedding_profile text NOT NULL,
    mode text NOT NULL,
    status text NOT NULL,
    data jsonb NOT NULL,
    PRIMARY KEY (run_id, call_id),
    FOREIGN KEY (run_id, scenario_id) REFERENCES llm_eval.scenarios(run_id, scenario_id),
    FOREIGN KEY (run_id, context_key) REFERENCES llm_eval.contexts(run_id, context_key)
);
CREATE INDEX IF NOT EXISTS calls_model_status ON llm_eval.calls(llm_profile, status);
CREATE TABLE IF NOT EXISTS llm_eval.reviews (
    run_id uuid NOT NULL,
    call_id text NOT NULL,
    reviewer text NOT NULL,
    data jsonb NOT NULL CHECK (jsonb_typeof(data) = 'object'),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, call_id, reviewer),
    FOREIGN KEY (run_id, call_id) REFERENCES llm_eval.calls(run_id, call_id)
);
