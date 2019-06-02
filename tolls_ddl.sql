USE tolls

CREATE TABLE ramp (
  ramp_id INT NOT NULL AUTO_INCREMENT,
  ramp_num INT NOT NULL,
  ramp_name VARCHAR(100) NOT NULL,
  CONSTRAINT PK_ramp PRIMARY KEY (ramp_id)
);

CREATE TABLE trip (
  trip_id INT NOT NULL AUTO_INCREMENT,
  ramp_on_id INT NOT NULL,
  ramp_off_id INT NOT NULL,
  CONSTRAINT PK_trip PRIMARY KEY (trip_id),
  CONSTRAINT FK_trip_ramp_on FOREIGN KEY (ramp_on_id) REFERENCES ramp (ramp_id),
  CONSTRAINT FK_trip_ramp_off FOREIGN KEY (ramp_off_id) REFERENCES ramp (ramp_id)
);

CREATE TABLE error_log (
  error_log_id INT NOT NULL AUTO_INCREMENT,
  error_log_date DATETIME NOT NULL,
  ramp_on INT NOT NULL,
  ramp_off INT NOT NULL,
  error_text VARCHAR(2000) NOT NULL,
  CONSTRAINT PK_error_log PRIMARY KEY (error_log_id)
);

CREATE INDEX IDX_error_log_date ON error_log (error_log_date DESC);

CREATE TABLE toll_log (
  toll_log_id INT NOT NULL AUTO_INCREMENT,
  toll_start_date DATETIME NOT NULL,
  toll_end_date DATETIME NOT NULL,
  ramp_on INT NOT NULL,
  ramp_off INT NOT NULL,
  price_495 NUMERIC(5,2),
  price_95 NUMERIC(5,2),
  direction CHAR(1) NOT NULL,
  CONSTRAINT PK_toll_log PRIMARY KEY (toll_log_id),
  CONSTRAINT CK_toll_log_date CHECK (toll_end_date >= toll_start_date),
  CONSTRAINT CK_toll_log_direction CHECK (direction IN ('N', 'S')),
  CONSTRAINT CK_toll_log_price CHECK (COALESCE(price_495, price_95) IS NOT NULL)
);

CREATE INDEX IDX_toll_log_date ON toll_log (toll_end_date DESC);

CREATE TABLE time_log (
  time_log_id INT NOT NULL AUTO_INCREMENT,
  time_start_date DATETIME NOT NULL,
  time_end_date DATETIME NOT NULL,
  ramp_on INT NOT NULL,
  ramp_off INT NOT NULL,
  time_495 INT,
  time_95 INT,
  direction CHAR(1) NOT NULL,
  CONSTRAINT PK_time_log PRIMARY KEY (time_log_id),
  CONSTRAINT CK_time_log_date CHECK (time_end_date >= time_start_date),
  CONSTRAINT CK_time_log_direction CHECK (direction IN ('N', 'S')),
  CONSTRAINT CK_time_log_time CHECK (COALESCE(time_495, 0) >= 0 AND COALESCE(time_95, 0) >= 0
    AND COALESCE(time_495, time_95) IS NOT NULL)
);

CREATE INDEX IDX_time_log_date ON time_log (time_end_date DESC);

CREATE TABLE reversible_log (
  reversible_log_id INT NOT NULL AUTO_INCREMENT,
  reversible_start_date DATETIME NOT NULL,
  reversible_end_date DATETIME NOT NULL,
  status_code CHAR(1) NOT NULL,
  CONSTRAINT PK_reversible_log PRIMARY KEY (reversible_log_id),
  CONSTRAINT CK_reversible_log_date CHECK (reversible_end_date >= reversible_start_date),
  CONSTRAINT CK_reversible_log_status_code CHECK (status_code IN ('N', 'S', 'C'))
);

CREATE INDEX IDX_reversible_end_date ON reversible_log (reversible_end_date DESC);
