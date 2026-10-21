"""건강 보완 CSV의 공개 영어 열 이름과 기존 모델 입력 이름 사이의 대응."""
import csv
import io


HEALTH_COLUMN_NAMES = {
    '자치구': 'sigungu_name',
    '행정동코드': 'region_code',
    '행정동명': 'region_name',
    '지역단위': 'geographic_unit',
    '의료자료기준': 'medical_reference_period',
    '인구기준': 'population_reference_period',
    '행정동주소DB기준': 'address_db_reference_period',
    '총인구': 'total_population',
    '고령인구비율_pct': 'elderly_population_pct',
    '의료기관수': 'medical_institution_count',
    '일반의원수': 'clinic_count',
    '약국수': 'pharmacy_count',
    '의과의사수': 'physician_count',
    '의과의사수_원본빈값수': 'physician_count_source_missing_count',
    '일반입원병상수': 'inpatient_bed_count',
    '일반입원병상수_원본빈값수': 'inpatient_bed_count_source_missing_count',
    '응급실병상수': 'emergency_bed_count',
    '응급실병상수_원본빈값수': 'emergency_bed_count_source_missing_count',
    '인구1만명당_의료기관수': 'medical_institutions_per_10000',
    '인구1만명당_일반의원수': 'clinics_per_10000',
    '인구1만명당_약국수': 'pharmacies_per_10000',
    '인구1만명당_의과의사수': 'physicians_per_10000',
    '인구1만명당_일반입원병상수': 'inpatient_beds_per_10000',
    '인구1만명당_응급실병상수': 'emergency_beds_per_10000',
    '공급량해석': 'medical_supply_note',
    '의료기관_원본목록완전연결': 'medical_source_link_complete',
    '약국_원본목록완전연결': 'pharmacy_source_link_complete',
    '제외기관중미연결의료기관_해당동가능수': 'excluded_unmapped_medical_candidate_count',
    '제외기관중미연결약국_해당동가능수': 'excluded_unmapped_pharmacy_candidate_count',
    '공공보건기관수': 'public_health_facility_count',
    '인구1만명당_공공보건기관수': 'public_health_facilities_per_10000',
    '의과병원수': 'hospital_count',
    '인구1만명당_의과병원수': 'hospitals_per_10000',
    '공식지정응급기관수': 'designated_emergency_institution_count',
    '기타응급실운영병원_명단기관수': 'other_emergency_roster_institution_count',
    '공식응급명단_기관수': 'emergency_roster_institution_count',
    '공식응급명단_기관보유': 'emergency_roster_present',
    '응급실병상기록_기관수': 'institutions_with_emergency_bed_records',
    '명시적24시간안내_기관수': 'explicit_24h_guidance_institution_count',
    '운영시간미확인_기관수': 'unknown_operating_hours_institution_count',
    '운영안내해석': 'operating_guidance_note',
    '응급명단기준일': 'emergency_roster_reference_date',
    '응급시설기준': 'emergency_facility_reference_period',
    '기준자료_연결확인': 'reference_link_confirmed',
    '응급자원_장점': 'emergency_resource_note',
    'emergency_presence_score': 'emergency_presence_score',
    'district_code': 'sigungu_code',
    'medical_eligible': 'medical_eligible',
    'age_eligible': 'age_eligible',
    'reference_eligible': 'reference_eligible',
    '고령인구비율_pct_종전': 'previous_elderly_population_pct',
    '고령인구_확인분합계': 'confirmed_elderly_population',
    '고령연령대_확인수': 'confirmed_elderly_age_band_count',
    '고령연령대_미확인수': 'missing_elderly_age_band_count',
    '고령연령대_미확인목록': 'missing_elderly_age_bands',
    '고령비율_자료상태': 'elderly_ratio_data_status',
    '고령비율_계산정책': 'elderly_ratio_policy',
}


def rename_health_csv_header(content, *, to_english=True):
    """첫 줄의 열 이름만 바꾸고 데이터 본문 바이트는 그대로 유지한다."""
    header, body = content.split(b'\n', 1)
    columns = next(csv.reader([header.decode('utf-8-sig').rstrip('\r')]))
    mapping = HEALTH_COLUMN_NAMES if to_english else {v: k for k, v in HEALTH_COLUMN_NAMES.items()}
    converted = [mapping.get(c, c) for c in columns]
    if len(converted) != len(set(converted)):
        raise ValueError('건강 CSV의 변환된 열 이름이 중복됩니다.')
    buffer = io.StringIO(newline='')
    csv.writer(buffer, lineterminator='\r\n' if header.endswith(b'\r') else '\n').writerow(converted)
    bom = b'\xef\xbb\xbf' if content.startswith(b'\xef\xbb\xbf') else b''
    return bom + buffer.getvalue().encode('utf-8') + body


def health_export_frame(frame):
    """공개 CSV는 영어 열 이름과 서울 접두·접미를 제외한 6자리 코드를 사용한다."""
    out = frame.rename(columns=HEALTH_COLUMN_NAMES).copy()
    codes = out['region_code'].astype(str)
    if not codes.str.fullmatch(r'11\d{6}00').all():
        raise ValueError('변환 전 행정동 코드는 11로 시작하고 00으로 끝나는 10자리여야 합니다.')
    out['region_code'] = codes.str.slice(2, -2)
    if out['region_code'].duplicated().any():
        raise ValueError('6자리 행정동 코드가 중복됩니다.')
    return out


def health_model_csv(content):
    """저장 모델에는 기존 열 이름과 10자리 코드를 전달한다."""
    legacy = rename_health_csv_header(content, to_english=False)
    rows = list(csv.reader(io.StringIO(legacy.decode('utf-8-sig'))))
    position = rows[0].index('행정동코드')
    for row in rows[1:]:
        code = row[position]
        if len(code) == 6 and code.isascii() and code.isdigit():
            row[position] = '11' + code + '00'
        elif not (len(code) == 10 and code.isascii() and code.isdigit()
                  and code.startswith('11') and code.endswith('00')):
            raise ValueError('건강 CSV의 행정동 코드 형식이 올바르지 않습니다.')
    buffer = io.StringIO(newline='')
    first_line = legacy.split(b'\n', 1)[0]
    csv.writer(buffer, lineterminator='\r\n' if first_line.endswith(b'\r') else '\n').writerows(rows)
    bom = b'\xef\xbb\xbf' if legacy.startswith(b'\xef\xbb\xbf') else b''
    return bom + buffer.getvalue().encode('utf-8')
