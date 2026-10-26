// 메인/상세 지도의 기존 5단계 색상 기준을 그대로 재사용합니다.
export function getScoreColor(score: number): string {
  if (score >= 60) return "#16a34a";
  if (score >= 40) return "#65a30d";
  if (score >= 20) return "#eab308";
  if (score >= 10) return "#f97316";
  return "#ef4444";
}
