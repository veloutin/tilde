CREATE TABLE tilde_home (
    id              SERIAL PRIMARY KEY,
    server_name     VARCHAR NULL,
    path            VARCHAR NULL,
    owner           VARCHAR NULL,
    groupname       VARCHAR NULL,

    uuid            VARCHAR NULL,
    ts              TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (server_name, path)
);

CREATE INDEX ids_home_ts ON tilde_home (ts);
CREATE INDEX ids_uuid ON tilde_home (uuid);
CREATE INDEX idx_home_server ON tilde_home (server_name);

CREATE TABLE tilde_home_state (
    id              INTEGER REFERENCES tilde_home(id),
    server_name     VARCHAR,
    path            VARCHAR,
    status          VARCHAR,
    ts              TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (id, server_name)
);
