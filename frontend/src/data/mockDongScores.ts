// 행정동별 AI 분석 점수 데이터 타입
export type DongScore = {
  dongCode: string;  // 행정동 코드 (GeoJSON의 adm_cd2)
  dongName: string;  // 행정동 이름
  district: string;  // 자치구 이름

  scores: {
    economy: number;  // 경제 활력도
    energy: number;   // 에너지 소비효율
    comfort: number;  // 생활 쾌적도
    health: number;   // 건강 안전도
    safety: number;   // 치안 안전도
  };
};

// 실제 AI 모델 연동 전 테스트 데이터
// [데이터 연결 대기] 실제 행정동 점수 또는 개발용 예시 데이터가 들어올 자리입니다.
export const mockDongScores: DongScore[] = [];

// 평가 항목별 가중치
export type ScoreWeights = {
  economy: number;
  energy: number;
  comfort: number;
  health: number;
  safety: number;
};

// 행정동별 종합점수 계산
// [종합점수 공식] Σ(항목점수×가중치)/Σ가중치; 모두 0이면 null입니다.
export function calculateTotalScore(
  scores: DongScore["scores"],
  weights: ScoreWeights
): number | null {
  const keys = [
    "economy",
    "energy",
    "comfort",
    "health",
    "safety",
  ] as const;

  const totalWeight = keys.reduce(
    (sum, key) => sum + weights[key],
    0
  );

  // 가중치 합계가 0이면 계산하지 않음
  if (totalWeight <= 0) return null;

  // 점수가 비정상이면 계산하지 않음
  if (
    keys.some(
      (key) =>
        !Number.isFinite(scores[key]) ||
        scores[key] < 0 ||
        scores[key] > 100
    )
  ) {
    return null;
  }

  const weightedSum = keys.reduce(
    (sum, key) => sum + scores[key] * weights[key],
    0
  );

  return weightedSum / totalWeight;
}

// 행정동 순위 데이터
export type RankedDong = DongScore & {
  totalScore: number;
  rank: number;
};

// 선택한 자치구의 행정동 TOP 10 계산
// [순위 계산] 선택 자치구 필터 → 종합점수 계산 → 내림차순 정렬 → 상위 10개 반환.
export function getTop10Dongs(
  dongScores: DongScore[],
  district: string,
  weights: ScoreWeights
): RankedDong[] {
  const ranked = dongScores
    .filter((dong) => dong.district === district)
    .map((dong) => ({
      ...dong,
      totalScore: calculateTotalScore(dong.scores, weights),
    }))
    .filter(
      (dong): dong is DongScore & { totalScore: number } =>
        dong.totalScore !== null
    )
    .sort(
      (a, b) =>
        b.totalScore - a.totalScore ||
        a.dongCode.localeCompare(b.dongCode)
    );

  return ranked.slice(0, 5).map((dong, index) => ({
    ...dong,
    rank: index + 1,
  }));
}

