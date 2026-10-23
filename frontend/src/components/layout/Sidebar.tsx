
import { useEffect, useState } from "react";
import "../../CSS/Sidebar.css";

type SidebarProps = {
  activeMenu: string;
  onMenuChange: (menu: string) => void;
};

// 기존 사이드바 메뉴
const menuGroups = [
  {
    menus: [
      "메인",
      "상세분석",
      "지역 비교",
    ],
  },
];

// 환경 관측 API 응답 타입
type AirQualityItem = {
  district: string;
  observed_at: string | null;
  pm25: number | null;
  pm10: number | null;
};

type AirQualityResponse = {
  source: string;
  count: number;
  items: AirQualityItem[];
};

// 기존 환경 노출 항목 유지
const exposureItems = [
  { label: "PM2.5", unit: "µg/m³" },
  { label: "PM10", unit: "µg/m³" },
];

export default function Sidebar({
  activeMenu,
  onMenuChange,
}: SidebarProps) {
  // 실제 대기환경 관측 데이터
  const [airQuality, setAirQuality] =
    useState<AirQualityItem[]>([]);

  // API 조회 상태
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  // 서울시 환경 관측 API 연결
  useEffect(() => {
    const controller = new AbortController();

    async function loadAirQuality() {
      try {
        setLoading(true);
        setError(false);

        const response = await fetch(
          "/api/environment/air-quality",
          { signal: controller.signal }
        );

        if (!response.ok) {
          throw new Error(
            `환경 관측 API 오류: ${response.status}`
          );
        }

        const data: AirQualityResponse =
          await response.json();

        setAirQuality(data.items ?? []);
      } catch (err) {
        if (!controller.signal.aborted) {
          console.error("환경 관측 데이터 조회 실패:", err);
          setError(true);
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    loadAirQuality();

    return () => controller.abort();
  }, []);

  // 서울시 자치구 관측값 산술평균
  function calculateAverage(
    key: "pm25" | "pm10"
  ): number | null {
    const values = airQuality
      .map((item) => item[key])
      .filter(
        (value): value is number =>
          typeof value === "number" &&
          Number.isFinite(value) &&
          value >= 0
      );

    if (values.length === 0) return null;

    return values.reduce(
      (sum, value) => sum + value,
      0
    ) / values.length;
  }

  const pm25 = calculateAverage("pm25");
  const pm10 = calculateAverage("pm10");

  // 값이 없는 항목은 임의의 수치를 넣지 않음
  function getExposureValue(label: string): string {
    if (label === "PM2.5") {
      return pm25 === null ? "--" : pm25.toFixed(1);
    }

    if (label === "PM10") {
      return pm10 === null ? "--" : pm10.toFixed(1);
    }

    return "--";
  }

  return (
    <aside className="sidebar">
      {/* 기존 로고 */}
      <div className="sidebar-logo">
        <div className="logo-icon">
          <svg
            width="19"
            height="19"
            viewBox="0 0 24 24"
            fill="none"
            stroke="white"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V10Z" />
            <path d="M9 21v-8h6v8" />
          </svg>
        </div>

        <div className="logo-text">
          <span>Seoul Smart Life</span>
          <p className="sub-title">
            맞춤형 주거지역 추천
          </p>
        </div>
      </div>

      {/* 기존 사이드바 메뉴 */}
      <nav className="sidebar-nav" aria-label="주 메뉴">
        {menuGroups.map((group) => (
          <div
            className="menu-group"
            key={group.menus.join("-")}
          >
            {group.menus.map((menu) => (
              <button
                type="button"
                key={menu}
                className={`menu-item ${
                  activeMenu === menu ? "active" : ""
                }`}
                onClick={() => onMenuChange(menu)}
                aria-current={
                  activeMenu === menu
                    ? "page"
                    : undefined
                }
              >
                {menu}
              </button>
            ))}
          </div>
        ))}
      </nav>

      {/* 환경 노출 지표 */}
      <div className="sidebar-exposure">
        <h3>환경 노출 지표</h3>

        <p className="sidebar-exposure-status">
          {loading
            ? "관측 데이터 불러오는 중"
            : error
              ? "환경 관측 API 연결 실패"
              : airQuality.length === 0
                ? "제공된 관측 데이터 없음"
                : "서울시 자치구 관측값 평균 연동 대기"}
        </p>

        {exposureItems.map((item) => (
          <div
            className="sidebar-exposure-item"
            key={item.label}
          >
            <span>{item.label}</span>

            <span className="sidebar-exposure-value">
              {getExposureValue(item.label)} {item.unit}
            </span>
          </div>
        ))}
      </div>
    </aside>
  );
}
