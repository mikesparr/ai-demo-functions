CREATE DATABASE IF NOT EXISTS bank_data;

USE bank_data;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS training (
    id UUID NOT NULL DEFAULT uuid_generate_v1(),
    variance DECIMAL,
    skewness DECIMAL,
    curtosis DECIMAL,
    entropy DECIMAL,
    class SMALLINT,
    created TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS predictions (
    id UUID NOT NULL DEFAULT uuid_generate_v1(),
    batch_id UUID,
    subject_id TEXT,
    variance DECIMAL,
    skewness DECIMAL,
    curtosis DECIMAL,
    entropy DECIMAL,
    prediction VARCHAR(48),
    is_correct BOOLEAN,
    created TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS jobs (
    id UUID NOT NULL DEFAULT uuid_generate_v1(),
    model_file_name VARCHAR(255),
    records INT,
    accuracy DECIMAL,
    report JSONB,
    data_prep_time DECIMAL,
    training_time DECIMAL,
    testing_time DECIMAL,
    created TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (id)
);

-- Create user 'ml_readwrite' --
GRANT SELECT, INSERT, UPDATE ON predictions TO ml_readwrite;
GRANT SELECT, INSERT ON training TO ml_readwrite;
GRANT INSERT ON jobs TO ml_readwrite;
