-- ===== 기준 테이블 =====
create table if not exists dim_region (
	region_code VARCHAR(10) primary key,
	region_name VARCHAR(50) not null,
	sigungu_code VARCHAR(5) not null,
	sigungu_name VARCHAR(30) not null,
	admin_code VARCHAR(10) not null,
	centroid_lat  DOUBLE PRECISION,
    centroid_lng  DOUBLE PRECISION,
    valid_from    DATE,
    valid_to      DATE
);

create table if not exists map_hjd_bjd(
	region_code VARCHAR(10) not null references dim_region (region_code),
	bjd_code VARCHAR(10) not null,
	bjd_name(50),
	primary KEY(region_code,bjd_code)
);
-- ===== 기상·대기·소음 (일별) =====
create table if not exists fact_weather(
	region_code VARCHAR(10) not null references dim_region(region_code),
	base_date DATE 			not NULL,
	avg_temp NUMERIC(5,2),
	max_temp NUMERIC(5,2),
	min_temp NUMERIC(5,2),
	humidity NUMERIC(5,2),
	uv_index NUMERIC(4,1),
	source_level VARCHAR(3) not null CHECK(source_level in ('HJD', 'SGG')),
	primary key (region_code, base_date)
);

create table if not exists fact_air(
	region_code VARCHAR(10) not null references dim_region(region_code),
	base_date DATE 			not null,
	pm10      NUMERIC(6,2),
	pm25	  NUMERIC(6,2),
	o3        NUMERIC(6,4),
	no2       NUMERIC(6,4),
	source_level VARCHAR(3) not null check (source_level in ('HJD','SGG')),
	primary key (region_code, base_date)
);

create table if not exists fact_noise(
	region_code VARCHAR(10) not null references dim_region(region_code),
	base_date DATE			not null,
	noise_day_db NUMERIC(5,2),
	noise_night_db NUMERIC(5,2),
	source_level VARCHAR(3) not null check (source_level in ('HJD','SGG')),
	primary key (region_code, base_date)	
);

-- ===== 인구·세대수·주택수 =====
create table if not exists fact_population(
	region_code VARCHAR(10) not null references dim_region (region_code),
	base_ym CHAR(6) 		not null,
	population INTEGER,
	source_level VARCHAR(3) not null check (source_level in ('HJD','SGG')),
	primary key (region_code, base_ym)
);

create table if not exists fact_households(
	region_code VARCHAR(10) not null references dim_region (region_code),
	base_ym CHAR(6) 		not null,
	households INTEGER,
	hh_1person INTEGER,
	primary key (region_code, base_ym)
);

create table if not exists fact_housing_stock(
	sigungu_code  VARCHAR(5)  NOT NULL,         
    base_year     INTEGER    NOT NULL,          
    housing_units INTEGER,                       
    PRIMARY KEY (sigungu_code, base_year)
);

-- ===== CCTV·범죄·에너지 =====
DROP TABLE IF EXISTS fact_crime;

CREATE TABLE fact_crime (
    sigungu_code            VARCHAR(5) NOT NULL,   -- 자치구 코드
    base_year               SMALLINT   NOT NULL,   -- 기준연도
    murder                  INTEGER,               -- 살인 발생
    robbery                 INTEGER,               -- 강도 발생
    sexual_assault          INTEGER,               -- 강간·강제추행 발생
    theft                   INTEGER,               -- 절도 발생
    violence                INTEGER,               -- 폭력 발생
    crime_total             INTEGER,               -- 5대범죄 발생 합계
    murder_cleared          INTEGER,               -- 살인 검거
    robbery_cleared         INTEGER,
    sexual_assault_cleared  INTEGER,
    theft_cleared           INTEGER,
    violence_cleared        INTEGER,
    cleared_total           INTEGER,               -- 5대범죄 검거 합계
    PRIMARY KEY (sigungu_code, base_year)
);

create table if not exists fact_energy_building(
 	region_code      VARCHAR(10) NOT NULL REFERENCES dim_region (region_code),
    base_ym          CHAR(6)     NOT NULL,
    electricity_Mwh  NUMERIC(14,2),
    gas_thousand_m3  NUMERIC(14,2),
    building_count   INTEGER,
    avg_building_age NUMERIC(5,1),
    source_level     VARCHAR(20)  NOT NULL CHECK (source_level IN ('HJD','SGG')),
    PRIMARY KEY (region_code, base_ym)
);

CREATE TABLE IF NOT EXISTS fact_cctv (
    sigungu_code          VARCHAR(5) NOT NULL,   -- 자치구 코드
    base_date             DATE       NOT NULL,   -- 기준일
    cctv_total            INTEGER,               -- CCTV 총계
    crime_prev_subtotal   INTEGER,               -- 범죄예방 및 수사 소계
    cctv_security         INTEGER,               -- 방범
    cctv_school_zone      INTEGER,               -- 어린이보호구역
    cctv_park_playground  INTEGER,               -- 공원·놀이터
    cctv_illegal_dumping  INTEGER,               -- 쓰레기 무단투기
    cctv_facility_safety  INTEGER,               -- 시설안전·화재예방
    cctv_traffic_enforce  INTEGER,               -- 교통단속
    cctv_traffic_info     INTEGER,               -- 교통정보수집·분석
    cctv_other            INTEGER,               -- 기타 다른법령
    PRIMARY KEY (sigungu_code, base_date)
);

CREATE TABLE IF NOT EXISTS fact_police_facility (
    sigungu_code         VARCHAR(5) NOT NULL,   -- 자치구 코드
    base_date            DATE       NOT NULL,   -- 기준일
    jigudae_count        INTEGER,               -- 지구대 수
    pachulso_count       INTEGER,               -- 파출소 수
    safety_center_count  INTEGER,               -- 치안센터 수
    PRIMARY KEY (sigungu_code, base_date)
);

CREATE TABLE IF NOT EXISTS public.dim_sigungu (
    sigungu_code VARCHAR(5) PRIMARY KEY,
    sigungu_name VARCHAR(30) NOT NULL
);

create table if not exists fact_air_monthly(
	station_name VARCHAR(30) not null,
	base_ym CHAR(6) not null,
	sigungu_code VARCHAR(5),
	pm10 		NUMERIC(6,2),
	pm2 		NUMERIC(6,2),
	o3    		NUMERIC(6,4),
	no2       	NUMERIC(6,4),
	co       	NUMERIC(6,2),
	so2			NUMERIC(6,4),
	primary key (station_name, base_ym)
);

create table if not exists fact_environment_exposure(
	year INTEGER,
	region_code VARCHAR(10),
	region_name VARCHAR(50),
	pollutant_type VARCHAR(30),
	facility_category VARCHAR(50),
	facility_count INTEGER
);

-- 1. 의료기관
CREATE TABLE IF NOT EXISTS fact_healthcare_institution (
    institution_id VARCHAR(100),
    institution_name VARCHAR(200),
    institution_type VARCHAR(50),
    region_code VARCHAR(10),
    region_name VARCHAR(50),
    admin_dong_code VARCHAR(10),
    admin_dong_name VARCHAR(50),
    address TEXT,
    phone VARCHAR(30),
    opened_date DATE,
    doctor_count INTEGER,
    general_bed_count INTEGER,
    emergency_bed_count INTEGER,
    longitude DOUBLE PRECISION,
    latitude DOUBLE PRECISION,
    source_period VARCHAR(20)
);

-- 2. 약국
CREATE TABLE IF NOT EXISTS fact_pharmacy (
    pharmacy_id VARCHAR(100),
    pharmacy_name VARCHAR(200),
    region_code VARCHAR(10),
    region_name VARCHAR(50),
    admin_dong_code VARCHAR(10),
    admin_dong_name VARCHAR(50),
    address TEXT,
    phone VARCHAR(30),
    opened_date DATE,
    longitude DOUBLE PRECISION,
    latitude DOUBLE PRECISION,
    source_period VARCHAR(20)
);

-- 3. 응급기관
CREATE TABLE IF NOT EXISTS fact_emergency_institution (
    institution_id VARCHAR(100),
    institution_name VARCHAR(200),
    emergency_type VARCHAR(100),
    pediatric_specialized BOOLEAN,
    trauma_center BOOLEAN,
    region_code VARCHAR(10),
    region_name VARCHAR(50),
    admin_dong_code VARCHAR(10),
    admin_dong_name VARCHAR(50),
    address TEXT,
    longitude DOUBLE PRECISION,
    latitude DOUBLE PRECISION,
    emergency_hours VARCHAR(100),
    source_date DATE
);

-- 4. 응급기관 운영 안내
CREATE TABLE IF NOT EXISTS fact_emergency_operation_guide (
    institution_id VARCHAR(100),
    institution_name VARCHAR(200),
    region_name VARCHAR(50),
    operation_text VARCHAR(200),
    operation_target VARCHAR(100),
    context_note TEXT,
    source_url TEXT
);

-- 5. 행정동 인구
CREATE TABLE IF NOT EXISTS fact_population_dong (
    admin_dong_code VARCHAR(10),
    region_name VARCHAR(50),
    admin_dong_name VARCHAR(50),
    base_period VARCHAR(20),
    total_population INTEGER,
    elderly_population INTEGER,
    child_population INTEGER,
    elderly_population_ratio DOUBLE PRECISION,
    child_population_ratio DOUBLE PRECISION
);

-- 기온 월별 --
CREATE TABLE fact_weather_monthly (
    sigungu_code VARCHAR(5) NOT NULL,
    base_date DATE NOT NULL,
    avg_temp NUMERIC,
    max_temp NUMERIC,
    min_temp NUMERIC,
    source_level VARCHAR(10) NOT NULL DEFAULT 'SGG',

    CONSTRAINT fact_weather_monthly_pkey
        PRIMARY KEY (sigungu_code, base_date),

    CONSTRAINT fk_weather_monthly_sigungu
        FOREIGN KEY (sigungu_code)
        REFERENCES dim_sigungu(sigungu_code)
);