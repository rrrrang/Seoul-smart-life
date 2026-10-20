
from pathlib import Path
import pandas as pd


# 프로젝트 경로
ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"

# 원본 파일: 2024년 1월 S-DoT 데이터
INPUT_FILE = RAW_DIR / "S-DoT_202401_정리.csv"

# 저장 파일
OUTPUT_FILE = PROCESSED_DIR / "S-DoT_202401_월평균.csv"


def main():
    # 1. 원본 CSV 읽기
    df = pd.read_csv(INPUT_FILE, encoding="utf-8-sig")

    # 컬럼명 앞뒤 공백 제거
    df.columns = df.columns.str.strip()

    print("원본 데이터 행 수:", len(df))
    print("원본 컬럼 목록:")
    print(df.columns.tolist())

    # 2. 날짜 컬럼 찾기
    date_candidates = [
        "측정일시",
        "측정시간",
        "수집일시",
        "일시",
        "datetime",
        "timestamp",
        "date",
    ]

    date_col = next(
        (col for col in date_candidates if col in df.columns),
        None,
    )

    if date_col is None:
        raise ValueError(
            "날짜 컬럼을 찾을 수 없습니다. "
            "위에 출력된 컬럼 목록을 확인하세요."
        )

    df[date_col] = pd.to_datetime(
        df[date_col],
        errors="coerce",
    )

    # 3. 2024년 1월 데이터만 선택
    df = df[
        (df[date_col].dt.year == 2024)
        & (df[date_col].dt.month == 1)
    ].copy()

    if df.empty:
        raise ValueError(
            "2024년 1월 데이터가 없습니다. 날짜 형식을 확인하세요."
        )

    # 4. 측정 지점 식별 컬럼 찾기
    station_candidates = [
        "측정소명",
        "측정지점",
        "지점명",
        "센서ID",
        "센서번호",
        "sensor_id",
    ]

    station_cols = [
        col for col in station_candidates
        if col in df.columns
    ]

    # 5. 숫자형 측정값만 평균 계산 대상으로 선택
    # 날짜 및 식별용 컬럼은 평균에서 제외
    exclude_cols = set(station_cols + [date_col])

    numeric_cols = [
        col for col in df.select_dtypes(include="number").columns
        if col not in exclude_cols
    ]

    if not numeric_cols:
        raise ValueError(
            "평균을 계산할 숫자형 측정값이 없습니다."
        )

    # 6. 월평균 집계
    if station_cols:
        result = (
            df.groupby(station_cols, dropna=False)[numeric_cols]
            .mean()
            .reset_index()
        )
    else:
        # 측정소 식별 컬럼이 없으면 전체 데이터의 월평균
        result = pd.DataFrame([df[numeric_cols].mean()])

    # 7. 월 정보 추가
    result.insert(0, "base_ym", "202401")

    # 8. CSV 저장
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    result = result.round(3)

    result.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print("\n===== 월평균 집계 완료 =====")
    print("집계 대상 원본 행 수:", len(df))
    print("측정 지점 식별 컬럼:", station_cols)
    print("평균 계산 컬럼:", numeric_cols)
    print("결과 행 수:", len(result))
    print("저장 경로:", OUTPUT_FILE)
    print(result.head())


if __name__ == "__main__":
    main()
