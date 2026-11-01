CREATE TABLE IF NOT EXISTS llm_eval.judge_jobs (
    id uuid PRIMARY KEY,
    run_id uuid NOT NULL,
    call_id text NOT NULL,
    input_hash text NOT NULL,
    config_hash text NOT NULL,
    attempt integer NOT NULL,
    status text NOT NULL CHECK (status IN ('running','completed','error','invalid')),
    input_data jsonb NOT NULL,
    config jsonb NOT NULL,
    usage jsonb,
    elapsed_s double precision,
    estimated_cost_usd double precision,
    error text,
    raw_output text,
    created_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    UNIQUE(run_id,call_id,input_hash,config_hash,attempt),
    FOREIGN KEY(run_id,call_id) REFERENCES llm_eval.calls(run_id,call_id)
);
CREATE TABLE IF NOT EXISTS llm_eval.judge_evaluations (
    job_id uuid PRIMARY KEY REFERENCES llm_eval.judge_jobs(id),
    data jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS llm_eval.judge_batches (
    id uuid PRIMARY KEY,
    status text NOT NULL CHECK(status IN ('draft','queued','running','completed','failed','cancelled')),
    settings jsonb NOT NULL,
    config jsonb NOT NULL,
    plan jsonb NOT NULL,
    stop_requested boolean NOT NULL DEFAULT false,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz
);
CREATE TABLE IF NOT EXISTS llm_eval.judge_batch_items (
    batch_id uuid REFERENCES llm_eval.judge_batches(id),
    ordinal integer NOT NULL,
    run_id uuid NOT NULL,
    call_id text NOT NULL,
    data jsonb NOT NULL,
    status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','skipped','completed','error','invalid','not_run')),
    job_id uuid REFERENCES llm_eval.judge_jobs(id),
    PRIMARY KEY(batch_id,ordinal),
    FOREIGN KEY(run_id,call_id) REFERENCES llm_eval.calls(run_id,call_id)
);
CREATE TABLE IF NOT EXISTS llm_eval.judge_worker_state (
    id integer PRIMARY KEY CHECK(id=1),
    updated_at timestamptz NOT NULL DEFAULT now(),
    info jsonb NOT NULL
);
