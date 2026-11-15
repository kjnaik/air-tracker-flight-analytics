-- Air Tracker: Flight Analytics schema (MySQL 8)

CREATE TABLE IF NOT EXISTS airport (
    airport_id  INT AUTO_INCREMENT PRIMARY KEY,
    icao_code   VARCHAR(10) UNIQUE,
    iata_code   VARCHAR(5)  UNIQUE,
    name        VARCHAR(255),
    city        VARCHAR(120),
    country     VARCHAR(120),
    continent   VARCHAR(50),
    latitude    DOUBLE,
    longitude   DOUBLE,
    timezone    VARCHAR(60)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS aircraft (
    aircraft_id    INT AUTO_INCREMENT PRIMARY KEY,
    registration   VARCHAR(20) UNIQUE,
    model          VARCHAR(120),
    manufacturer   VARCHAR(120),
    icao_type_code VARCHAR(10),
    owner          VARCHAR(255)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS flights (
    flight_id              VARCHAR(100) PRIMARY KEY,
    flight_number          VARCHAR(20),
    aircraft_registration  VARCHAR(20),
    origin_iata            VARCHAR(5),
    destination_iata       VARCHAR(5),
    scheduled_departure    DATETIME NULL,
    actual_departure       DATETIME NULL,
    scheduled_arrival      DATETIME NULL,
    actual_arrival         DATETIME NULL,
    status                 VARCHAR(30),
    airline_code           VARCHAR(10),
    airline_name           VARCHAR(120),
    delay_minutes          INT NULL,
    CONSTRAINT fk_flights_origin
        FOREIGN KEY (origin_iata) REFERENCES airport(iata_code)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_flights_destination
        FOREIGN KEY (destination_iata) REFERENCES airport(iata_code)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_flights_aircraft
        FOREIGN KEY (aircraft_registration) REFERENCES aircraft(registration)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS airport_delays (
    delay_id          INT AUTO_INCREMENT PRIMARY KEY,
    airport_iata      VARCHAR(5),
    delay_date        DATE,
    total_flights     INT,
    delayed_flights   INT,
    delay_index       DOUBLE,
    median_delay_min  INT,
    canceled_flights  INT,
    UNIQUE KEY uq_airport_date (airport_iata, delay_date),
    CONSTRAINT fk_delays_airport
        FOREIGN KEY (airport_iata) REFERENCES airport(iata_code)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB;

-- Indexes for query performance
CREATE INDEX idx_flights_origin      ON flights (origin_iata);
CREATE INDEX idx_flights_destination ON flights (destination_iata);
CREATE INDEX idx_flights_aircraft    ON flights (aircraft_registration);
CREATE INDEX idx_flights_status      ON flights (status);
CREATE INDEX idx_flights_airline     ON flights (airline_code);
CREATE INDEX idx_flights_sched_dep   ON flights (scheduled_departure);
CREATE INDEX idx_flights_sched_arr   ON flights (scheduled_arrival);
CREATE INDEX idx_airport_country     ON airport (country);