import { useEffect, useMemo, useState } from "react";
import { mockDongScores, calculateTotalScore, type DongScore } from "../data/mockDongScores";
import "../CSS/RegionComparison.css";

// 실제 서버 데이터 연동 시 이 배열 대신 API 응답을 넘겨주면 됩니다.
// 지역 식별은 이름이 아닌 행정동 코드(adm_cd2)를 기준으로 합니다.
type DongOption = { code: string; name: string; district: string };
type ChartMode = "bar" | "radar";
const metrics = [
  { key: "economy", label: "경제 활력도" },
  { key: "energy", label: "에너지 소비효율" },
  { key: "comfort", label: "생활 쾌적도" },
  { key: "health", label: "건강 안전도" },
  { key: "safety", label: "치안 안전도" },
] as const;
const defaultWeights = { economy: 20, energy: 15, comfort: 25, health: 20, safety: 20 };

type GeoFeature = {
  properties?: Record<string, unknown>;
};
type GeoJson = { features?: GeoFeature[] };

// GeoJSON마다 다른 행정동 이름 필드를 안전하게 처리합니다.
function getText(properties: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = properties[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function scoreOf(data: DongScore | undefined, key: (typeof metrics)[number]["key"]): number | null {
  const value = data?.scores[key];
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100 ? value : null;
}

function RadarChart({ a, b }: { a?: DongScore; b?: DongScore }) {
  const center = 150;
  const radius = 100;
  const point = (i: number, value: number) => {
    const angle = -Math.PI / 2 + (2 * Math.PI * i) / 5;
    return `${center + Math.cos(angle) * radius * (value / 100)},${center + Math.sin(angle) * radius * (value / 100)}`;
  };
  const polygon = (data: DongScore) => metrics.map((item, i) => point(i, scoreOf(data, item.key) ?? 0)).join(" ");
  // 누락된 지표가 있다면 그래프를 그리지 않습니다.
  if (!a || !b || metrics.some((m) => scoreOf(a, m.key) === null || scoreOf(b, m.key) === null)) {
    return <div className="comparison-pending">두 지역의 5개 지표가 모두 연결되면 레이더 차트를 표시합니다.</div>;
  }
  return (
    <div className="comparison-radar-wrap">
      <svg viewBox="-22 -20 344 342" role="img" aria-label="지역 A와 B의 다섯 지표 레이더 차트">
        {[20, 40, 60, 80, 100].map((v) => (
          <polygon key={v} points={metrics.map((_, i) => point(i, v)).join(" ")} fill="none" stroke="#dde1eb" strokeWidth="1" />
        ))}
        {metrics.map((metric, i) => {
          const angle = -Math.PI / 2 + (2 * Math.PI * i) / 5;
          return (
            <g key={metric.key}>
              <line x1={center} y1={center} x2={center + Math.cos(angle) * radius} y2={center + Math.sin(angle) * radius} stroke="#dde1eb" />
              <text x={center + Math.cos(angle) * (radius + 22)} y={center + Math.sin(angle) * (radius + 22)} textAnchor="middle" dominantBaseline="middle" fontSize="11" fill="#5c6477">{["경제", "에너지", "쾌적", "건강", "치안"][i]}</text>
            </g>
          );
        })}
        <polygon points={polygon(a)} fill="#64748b" fillOpacity="0.15" stroke="#64748b" strokeWidth="2.5" />
        <polygon points={polygon(b)} fill="#6457db" fillOpacity="0.15" stroke="#6457db" strokeWidth="2.5" />
      </svg>
      <div className="comparison-legend"><span><i className="legend-a" /> 지역 A</span><span><i className="legend-b" /> 지역 B</span></div>
    </div>
  );
}

export default function RegionComparison() {
  const [options, setOptions] = useState<DongOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [regionA, setRegionA] = useState("");
  const [regionB, setRegionB] = useState("");
  const [chartMode, setChartMode] = useState<ChartMode>("bar");

  // 지도 GeoJSON에서 실제 행정동 선택 목록을 가져옵니다.
  useEffect(() => {
    let cancelled = false;
    fetch("/data/seoul_dong.geojson")
      .then((response) => {
        if (!response.ok) throw new Error("행정동 GeoJSON을 불러올 수 없습니다.");
        return response.json() as Promise<GeoJson>;
      })
      .then((json) => {
        if (cancelled) return;
        const dedup = new Map<string, DongOption>();
        for (const feature of json.features ?? []) {
          const p = feature.properties ?? {};
          const code = String(p.adm_cd2 ?? "").trim();
          const name = getText(p, ["adm_nm", "admnm", "adm_name", "dong_name", "dongName", "행정동명"]);
          const district = getText(p, ["sggnm", "sgg_nm", "district", "시군구명"]);
          // adm_nm 값이 '서울특별시 종로구 청운효자동'처럼 전체 경로인 경우에는 마지막 이름을 사용합니다.
          const shortName = name.split(/\s+/).at(-1) ?? "";
          if (code && shortName) dedup.set(code, { code, name: shortName, district });
        }
        // 점수 데이터에만 등록된 동도 선택 가능하도록 병합합니다.
        for (const dong of mockDongScores) {
          if (!dedup.has(dong.dongCode)) dedup.set(dong.dongCode, { code: dong.dongCode, name: dong.dongName, district: dong.district });
        }
        setOptions([...dedup.values()].sort((x, y) => x.district.localeCompare(y.district, "ko") || x.name.localeCompare(y.name, "ko")));
      })
      .catch(() => {
        if (!cancelled) {
          setLoadError(true);
          setOptions(mockDongScores.map((d) => ({ code: d.dongCode, name: d.dongName, district: d.district })));
        }
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const selectedA = options.find((item) => item.code === regionA);
  const selectedB = options.find((item) => item.code === regionB);
  const scoreA = mockDongScores.find((item) => item.dongCode === regionA);
  const scoreB = mockDongScores.find((item) => item.dongCode === regionB);
  // 비교 페이지는 현재 기본 가중치를 사용합니다. 이후 App의 공통 가중치 상태로 교체할 수 있습니다.
  const totalA = useMemo(() => scoreA ? calculateTotalScore(scoreA.scores, defaultWeights) : null, [scoreA]);
  const totalB = useMemo(() => scoreB ? calculateTotalScore(scoreB.scores, defaultWeights) : null, [scoreB]);
  const ready = selectedA && selectedB && regionA !== regionB;

  return (
    <section className="comparison-page">
      <header className="comparison-header">
        <div className="comparison-heading-icon">✦</div>
        <div><h1>지역 비교 분석</h1><p>두 행정동의 생활환경 지표를 비교하고 강점과 차이를 확인하세요.</p></div>
        <span className="comparison-status">분석 데이터 연동 예정</span>
      </header>

      <section className="comparison-card comparison-select-card" aria-label="비교 지역 선택">
        <div className="comparison-section-heading"><h2>비교할 지역 선택</h2><p>행정동 단위로 두 지역을 선택하세요.</p></div>
        <div className="comparison-select-grid">
          <label>지역 A
            <select value={regionA} onChange={(e) => setRegionA(e.target.value)} disabled={loading}>
              <option value="">{loading ? "행정동 목록 불러오는 중..." : "행정동을 선택하세요"}</option>
              {options.map((option) => <option key={option.code} value={option.code}>{option.district ? `${option.district} · ` : ""}{option.name}</option>)}
            </select>
          </label>
          <span className="comparison-vs">VS</span>
          <label>지역 B
            <select value={regionB} onChange={(e) => setRegionB(e.target.value)} disabled={loading}>
              <option value="">{loading ? "행정동 목록 불러오는 중..." : "행정동을 선택하세요"}</option>
              {options.map((option) => <option key={option.code} value={option.code}>{option.district ? `${option.district} · ` : ""}{option.name}</option>)}
            </select>
          </label>
        </div>
        {loadError && <p className="comparison-note">행정동 목록 파일을 읽지 못했습니다. public/data/seoul_dong.geojson 경로를 확인해 주세요.</p>}
        {regionA && regionB && regionA === regionB && <p className="comparison-note">서로 다른 행정동을 선택해 주세요.</p>}
      </section>

      <div className="comparison-score-grid">
        {([{ title: "지역 A 종합점수", region: selectedA, total: totalA }, { title: "지역 B 종합점수", region: selectedB, total: totalB }] as const).map((item) => (
          <section className="comparison-card comparison-score-card" key={item.title}>
            <span className="comparison-muted">{item.title}</span>
            <h2>{item.region ? `${item.region.district} ${item.region.name}` : "지역 선택 대기"}</h2>
            <div className="comparison-big-score">{ready && item.total !== null ? item.total.toFixed(1) : "--"}<span> / 100점</span></div>
            <p className="comparison-muted">{ready && item.total !== null ? "기본 가중치 적용" : "평가 점수 데이터 연동 대기"}</p>
          </section>
        ))}
      </div>

      <section className="comparison-card comparison-chart-card">
        <div className="comparison-chart-header">
          <div className="comparison-section-heading"><h2>항목별 생활환경 비교</h2><p>경제·에너지·쾌적·건강·치안의 5개 지표를 비교합니다.</p></div>
          <div className="comparison-tabs" role="group" aria-label="그래프 유형">
            <button type="button" className={chartMode === "bar" ? "active" : ""} aria-pressed={chartMode === "bar"} onClick={() => setChartMode("bar")}>막대그래프</button>
            <button type="button" className={chartMode === "radar" ? "active" : ""} aria-pressed={chartMode === "radar"} onClick={() => setChartMode("radar")}>레이더 차트</button>
          </div>
        </div>
        {!ready ? <div className="comparison-pending">비교할 두 행정동을 선택하면 분석 결과를 확인할 수 있습니다.</div> : chartMode === "radar" ? <RadarChart a={scoreA} b={scoreB} /> : (
          <div className="comparison-bars">
            <div className="comparison-legend"><span><i className="legend-a" /> {selectedA.name}</span><span><i className="legend-b" /> {selectedB.name}</span></div>
            {metrics.map((m) => {
              const a = scoreOf(scoreA, m.key);
              const b = scoreOf(scoreB, m.key);
              return <div className="comparison-metric" key={m.key}>
                <h3>{m.label}</h3>
                <div className="comparison-bar-row"><span>A</span><div className="comparison-track"><div className="comparison-fill-a" style={{ width: `${a ?? 0}%` }} /></div><strong>{a === null ? "--" : a.toFixed(1)}</strong></div>
                <div className="comparison-bar-row"><span>B</span><div className="comparison-track"><div className="comparison-fill-b" style={{ width: `${b ?? 0}%` }} /></div><strong>{b === null ? "--" : b.toFixed(1)}</strong></div>
              </div>;
            })}
            {(!scoreA || !scoreB) && <p className="comparison-note">선택한 행정동의 평가 점수는 아직 연결되지 않았습니다.</p>}
          </div>
        )}
      </section>

      <section className="comparison-card comparison-insight">
        <h2>✦ AI 비교 인사이트</h2>
        <p>분석 데이터가 연결되면 두 지역의 강점, 취약 지표, 종합점수 차이 및 추천 근거를 이곳에 표시합니다.</p>
      </section>
    </section>
  );
}
