import { useEffect, useRef, useState } from "react";
import "../CSS/SeoulMap.css";
import { getScoreColor } from "../utils/scoreColor";

// Kakao Maps JavaScript SDK 타입 (별도 타입 패키지가 없는 경우)
declare global {
  interface Window {
    kakao: any;
  }
}

type RegionScore = {
  district: string;
  score: number;
};

type Props = {
  data: RegionScore[];
  selectedDistrict?: string | null;
  onDistrictClick?: (district: string) => void;

  // 메인 지도에서 더블클릭 시 페이지 이동
  onDistrictDoubleClick?: (district: string) => void;

  // 상세분석에서 확대할 자치구
  focusDistrict?: string | null;
  resetKey?: number;
  dongScores?: { dongCode: string; score: number }[];
  selectedDongCode?: string | null;
  onDongClick?: (dongCode: string) => void;
};

// GeoJSON 좌표는 [경도, 위도] 순서
type Coordinate = [number, number];
type Ring = Coordinate[];
type PolygonCoordinates = Ring[];
type MultiPolygonCoordinates = PolygonCoordinates[];

type DistrictFeature = {
  type: "Feature";
  properties: Record<string, unknown> | null;
  geometry:
    | { type: "Polygon"; coordinates: PolygonCoordinates }
    | { type: "MultiPolygon"; coordinates: MultiPolygonCoordinates };
};

type DistrictGeoJSON = {
  type: "FeatureCollection";
  features: DistrictFeature[];
};

// 여러 컴포넌트가 마운트되더라도 SDK 스크립트는 한 번만 요청
let sdkPromise: Promise<void> | null = null;

// [SDK 로딩] 중복 로드를 방지하며 카카오 지도 SDK를 비동기로 준비합니다.
function loadKakaoSDK(): Promise<void> {
  if (window.kakao?.maps?.Map) return Promise.resolve();
  if (sdkPromise) return sdkPromise;

  const key = import.meta.env.VITE_KAKAO_MAP_KEY;
  if (!key) {
    return Promise.reject(
      new Error("VITE_KAKAO_MAP_KEY가 없습니다. frontend/.env를 확인하세요.")
    );
  }

  const request = new Promise<void>((resolve, reject) => {
    // React StrictMode에서도 중복 script가 생기지 않도록 ID 사용
    const scriptId = "kakao-maps-sdk";
    let script = document.getElementById(scriptId) as HTMLScriptElement | null;
    let finished = false;

    const timeoutId = window.setTimeout(() => {
      finish(new Error("카카오맵 SDK 로딩 시간 초과 (15초)"));
    }, 15000);

    function finish(error?: Error) {
      if (finished) return;
      finished = true;
      window.clearTimeout(timeoutId);
      if (error) reject(error);
      else resolve();
    }

    function initialize() {
      if (!window.kakao?.maps?.load) {
        finish(new Error("카카오맵 SDK 초기화에 실패했습니다."));
        return;
      }
      window.kakao.maps.load(() => finish());
    }

    if (script) {
      // 이전 로딩 시도가 남긴 script를 재사용
      if (window.kakao?.maps?.load) {
        initialize();
      } else {
        script.addEventListener("load", initialize, { once: true });
        script.addEventListener(
          "error",
          () => finish(new Error("카카오맵 SDK 네트워크 요청 실패")),
          { once: true }
        );
      }
      return;
    }

    script = document.createElement("script");
    script.id = scriptId;
    script.src =
      "https://dapi.kakao.com/v2/maps/sdk.js" +
      `?appkey=${encodeURIComponent(key)}` +
      "&autoload=false";
    script.async = true;
    script.addEventListener("load", initialize, { once: true });
    script.addEventListener(
      "error",
      () => finish(new Error("카카오맵 SDK 네트워크 요청 실패")),
      { once: true }
    );
    document.head.appendChild(script);
  });

  sdkPromise = request.catch((error) => {
    sdkPromise = null;
    // 실패한 script는 재시도 가능하도록 제거
    document.getElementById("kakao-maps-sdk")?.remove();
    throw error;
  });
  return sdkPromise;
}

// [지도 색상] 0~100점 점수를 구간별 색상으로 변환합니다.
function getColor(score: number): string {
  return getScoreColor(score);
}

// [자치구 이름] GeoJSON마다 다른 속성 이름을 하나로 읽습니다.
function getDistrictName(feature: DistrictFeature): string {
  const props = feature.properties;
  const value = props?.name ?? props?.SIG_KOR_NM ?? props?.sggnm ?? "";
  return typeof value === "string" ? value : String(value);
}

// [좌표 변환] GeoJSON [경도,위도]를 카카오맵 LatLng(위도,경도)로 바꿉니다.
function convertRing(ring: Ring): any[] {
  return ring.map(([lng, lat]) => new window.kakao.maps.LatLng(lat, lng));
}

// [지도 컴포넌트] 상위 페이지에서 선택 지역, 점수 및 초기화 신호를 전달받습니다.
export default function SeoulMap({
  data,
  selectedDistrict,
  onDistrictClick,
  onDistrictDoubleClick,
  focusDistrict,
  resetKey,
  dongScores = [],
  selectedDongCode,
  onDongClick,
}: Props) {
  const mapRef = useRef<HTMLDivElement>(null);
  const [map, setMap] = useState<any>(null);
  const [geoData, setGeoData] = useState<DistrictGeoJSON | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [geoReady, setGeoReady] = useState(false);
  const [polygonsReady, setPolygonsReady] = useState(false);
  const [tilesReady, setTilesReady] = useState(false);
  const onClickRef = useRef(onDistrictClick);
  const onDongClickRef = useRef(onDongClick);
  const dongPopupInfoRef = useRef<{ code: string; name: string; position: any } | null>(null);
  useEffect(() => { 
    onDongClickRef.current = onDongClick; 
  }, [onDongClick]);
  // 더블클릭 콜백을 최신 상태로 유지
  const onDoubleClickRef = useRef(onDistrictDoubleClick);
  // 마지막으로 클릭한 자치구와 클릭 시간 저장
  const lastClickRef = useRef<{
    district: string;
    time: number;
  } | null>(null);

  useEffect(() => {
    onDoubleClickRef.current = onDistrictDoubleClick;
  }, [onDistrictDoubleClick]);

  // 이벤트 핸들러를 다시 등록하지 않고 최신 콜백만 유지
  useEffect(() => {
    onClickRef.current = onDistrictClick;
  }, [onDistrictClick]);

  // [지도 생성] 최초 마운트 시 지도 객체를 생성하고 타일 로딩을 감시합니다.
  // 1. 카카오맵 SDK 로드 및 지도 생성
  useEffect(() => {
    let cancelled = false;
    let tileHandler: (() => void) | null = null;
    let createdMap: any = null;
    let fallbackTimer: number | undefined;

    loadKakaoSDK()
      .then(() => {
        if (cancelled || !mapRef.current) return;
        const kakao = window.kakao;
        createdMap = new kakao.maps.Map(mapRef.current, {
          center: new kakao.maps.LatLng(37.5665, 126.978),
          level: 9,
          disableDoubleClickZoom: true, // 더블클릭 시 지도 자동 확대 방지
        });


        // 지도 생성 후 바로 이벤트 등록 (초기 tilesloaded 놓침 방지)
        tileHandler = () => {
          if (!cancelled) setTilesReady(true);
        };
        kakao.maps.event.addListener(createdMap, "tilesloaded", tileHandler);

        // tilesloaded가 오지 않더라도 로딩 오버레이가 영구적으로 남지 않도록
        // 타일 대기만 종료 (실제 타일 수신 성공을 보장하지는 않음)
        fallbackTimer = window.setTimeout(() => {
          if (!cancelled) setTilesReady(true);
        }, 8000);

        setMap(createdMap);
        setMapReady(true);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "지도 SDK 오류");
        }
      });

    return () => {
      cancelled = true;
      if (fallbackTimer !== undefined) window.clearTimeout(fallbackTimer);
      if (createdMap && tileHandler) {
        window.kakao.maps.event.removeListener(
          createdMap,
          "tilesloaded",
          tileHandler
        );
      }
      // StrictMode 재마운트 시 DOM과 연결된 기존 객체 참조 정리
      setMap(null);
    };
  }, []);

  // [자치구 데이터] public/data/seoul.geojson을 가져와 자치구 경계를 읽습니다.
  // 2. 서울 행정구역 GeoJSON 로드
  useEffect(() => {
    const controller = new AbortController();
    fetch("/data/seoul.geojson", { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error(`서울 GeoJSON 요청 실패 (${res.status})`);
        return res.json();
      })
      .then((json: DistrictGeoJSON) => {
        if (json.type !== "FeatureCollection" || !Array.isArray(json.features)) {
          throw new Error("서울 지도 파일이 GeoJSON FeatureCollection이 아닙니다.");
        }
        setGeoData(json);
        setGeoReady(true);
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : "GeoJSON 읽기 실패");
        }
      });
    return () => controller.abort();
  }, []);

  // [지도 확대 A] 선택한 자치구의 경계 좌표를 지도 화면에 맞춰 자동 확대합니다.
  // 선택한 자치구 자동 확대 (새로 추가)
  useEffect(() => {
    if (!map || !geoData || !focusDistrict) return;
  
    const kakao = window.kakao;
  
    // 선택한 자치구 찾기
    const feature = geoData.features.find(
      (item) => getDistrictName(item) === focusDistrict
    );
  
    if (!feature || !feature.geometry) return;
  
    const bounds = new kakao.maps.LatLngBounds();
  
    const polygonGroups: PolygonCoordinates[] =
      feature.geometry.type === "Polygon"
        ? [feature.geometry.coordinates]
        : feature.geometry.coordinates;
  
    // 선택한 자치구의 경계 좌표
    for (const rings of polygonGroups) {
    for (const ring of rings) {
      for (const [lng, lat] of ring) {
        bounds.extend(new kakao.maps.LatLng(lat, lng));
      }
    }
    }
  
    // 선택한 구가 지도 안에 들어오도록 자동 확대
    map.setBounds(bounds, 40, 40, 40, 40);
    // 상세분석 페이지 진입 시 한 단계 더 확대
    map.setLevel(Math.max(1, map.getLevel() - 1));
  }, [map, geoData, focusDistrict]);

  // ★ [지도 확대 B] 초기화 버튼을 누르면 서울 전체 자치구 범위로 지도를 복원합니다.
  // 초기화 버튼을 누르면 서울 전체 지도 표시
  useEffect(() => {
    if (!map || !geoData || !resetKey) return;
  
    const kakao = window.kakao;
    const bounds = new kakao.maps.LatLngBounds();
  
    // 서울 25개 자치구의 전체 경계 좌표 수집
    for (const feature of geoData.features) {
      const geometry = feature.geometry;
      if (!geometry) continue;
  
      const polygonGroups: PolygonCoordinates[] =
        geometry.type === "Polygon"
          ? [geometry.coordinates]
          : geometry.coordinates;
  
      for (const rings of polygonGroups) {
        for (const ring of rings) {
          for (const [lng, lat] of ring) {
            bounds.extend(new kakao.maps.LatLng(lat, lng));
          }
        }
      }
    }
  
    // 서울 전체가 지도 안에 들어오도록 확대 수준 조정
    map.setBounds(bounds, 30, 30, 30, 30);
  }, [map, geoData, resetKey]);


  // 행정동 경계선 표시
  useEffect(() => {

    if (!map) return;
  
    let cancelled = false;
    const dongPolygons: any[] = [];
  
    fetch("/data/seoul_dong.geojson")
      .then((response) => {
        if (!response.ok) {
          throw new Error("행정동 GeoJSON 파일을 불러오지 못했습니다.");
        }
        return response.json();
      })
      .then((geojson) => {
        if (cancelled) return;
  
        const kakao = window.kakao;

        // 백엔드에서 전달받은 행정동별 종합점수를 코드 기준으로 조회
        const dongScoreMap = new Map(dongScores.map((item) => [item.dongCode, item.score]));
        
        for (const feature of geojson.features) {

          // 상세분석에서는 선택된 구의 행정동만 표시
          if (focusDistrict && feature.properties?.sggnm !== focusDistrict) {
            continue;
          }

          const geometry = feature.geometry;
          if (!geometry) continue;
  
          const polygonGroups =
            geometry.type === "Polygon"
              ? [geometry.coordinates]
              : geometry.type === "MultiPolygon"
                ? geometry.coordinates
                : [];
  
          for (const rings of polygonGroups) {
            // 행정동 코드 가져오기
            const dongCode = String(feature.properties?.adm_cd2 ?? "");
          
            // 행정동 코드로 AI 분석 점수 조회
            const score = dongScoreMap.get(dongCode);
            const isSelectedDong = !!selectedDongCode && selectedDongCode === dongCode;
          
            const polygon = new kakao.maps.Polygon({
              map,
              path: rings.map(convertRing),
          
              // 행정동 경계선
              strokeWeight: isSelectedDong ? 4 : 1,
              strokeColor: isSelectedDong ? "#4f46e5" : "#94a3b8",
              strokeOpacity: isSelectedDong ? 1 : 0.7,
          
              // AI 분석 점수에 따른 색상
              fillColor: score !== undefined ? getColor(score) : "#ffffff",
              fillOpacity: score !== undefined ? 0.45 : 0.2,
          
              // 행정동 폴리곤은 색상 전용이며 클릭은 자치구가 처리
              // 자치구가 확대된 상태에서만 행정동 클릭 활성화
              clickable: Boolean(focusDistrict && onDongClickRef.current),
              
              // 확대 전에는 자치구가 위, 확대 후에는 행정동이 위
              zIndex: focusDistrict
                ? (isSelectedDong ? 7 : 5)
                : 3,
            });
          
            // 자치구 확대 상태에서만 행정동 선택
            if (focusDistrict && onDongClickRef.current) {
              kakao.maps.event.addListener(polygon, "click", (event: any) => {
                // 실제 클릭 위치를 저장해 지도 위에 점수 표시
                const name = String(feature.properties?.adm_nm ?? feature.properties?.name ?? dongCode);
                const dongName = name.includes(" ") ? name.split(" ").at(-1) ?? name : name;
                dongPopupInfoRef.current = { code: dongCode, name: dongName, position: event.latLng };
                onDongClickRef.current?.(dongCode);
              });
            }
            dongPolygons.push(polygon);
          }
        }
      })
      .catch((error) => {
        if (!cancelled) {
          console.error("행정동 경계 오류:", error);
        }
      });
  
    return () => {
      cancelled = true;
      dongPolygons.forEach((polygon) => polygon.setMap(null));
    };
  }, [map, focusDistrict, dongScores, selectedDongCode]);

  // 행정동 점수 팝업: 클릭한 지리 좌표에 표시 (디자인은 SeoulMap.css)
  useEffect(() => {
    if (!map || !focusDistrict || !selectedDongCode) return;
    const clicked = dongPopupInfoRef.current;
    if (!clicked || clicked.code !== selectedDongCode) return;

    const score = dongScores.find((item) => item.dongCode === selectedDongCode)?.score;
    const content = document.createElement("div");
    content.className = "dong-score-popup";
    const name = document.createElement("div");
    name.className = "dong-score-popup__name";
    name.textContent = clicked.name;
    const value = document.createElement("strong");
    value.className = "dong-score-popup__value";
    value.textContent = score === undefined ? "AI 종합점수 데이터 없음" : `AI 종합점수 ${score.toFixed(1)}점`;
    content.append(name, value);

    const overlay = new window.kakao.maps.CustomOverlay({
      map,
      position: clicked.position,
      content,
      yAnchor: 1.2,
      zIndex: 12,
    });
    return () => overlay.setMap(null);
  }, [map, focusDistrict, selectedDongCode, dongScores]);

  // 3. 자치구 Polygon, 지역명 오버레이 생성
  useEffect(() => {
    if (!map || !geoData) return;

    const kakao = window.kakao;
    const polygons: any[] = [];
    const outsidePolygons: any[] = [];
    // 자치구 이름 오버레이: 해당 useEffect 생성/정리 범위에서 관리
    const districtLabels: any[] = [];
    const scoreMap = new Map(data.map((item) => [item.district, item.score]));

    // 서울 외부 영역에 반투명 회색 음영 적용
    const outerPath = [
      new kakao.maps.LatLng(38.5, 125.5),
      new kakao.maps.LatLng(38.5, 128.5),
      new kakao.maps.LatLng(36.5, 128.5),
      new kakao.maps.LatLng(36.5, 125.5),
    ];
    
    const seoulHoles = geoData.features.flatMap((feature) => {
      if (feature.geometry.type === "Polygon") {
        return [feature.geometry.coordinates[0]];
      }
    
      return feature.geometry.coordinates.map((polygon) => polygon[0]);
    });
    
    // 서울 외부 지역을 회색으로 덮는 마스크(Polygon)
    const mask = new kakao.maps.Polygon({
      map,
      path: [
        outerPath,
        ...seoulHoles.map((ring) => convertRing(ring)),
      ],
      strokeWeight: 0,
      fillColor: "#64748b",
      fillOpacity: 0.38,
      zIndex: 1,
    });
    
    outsidePolygons.push(mask);

    try {
      for (const feature of geoData.features) {
        const name = getDistrictName(feature);
        if (!name || !feature.geometry) continue;
        const score = scoreMap.get(name);
        const polygonGroups: PolygonCoordinates[] =
          feature.geometry.type === "Polygon"
            ? [feature.geometry.coordinates]
            : feature.geometry.coordinates;

        for (const rings of polygonGroups) {
          if (!rings.length) continue;
          const paths = rings.map(convertRing);
          // 자치구 폴리곤은 클릭 이벤트를 담당하고, 행정동 색상은 가리지 않습니다.
          // 백엔드 점수 로딩과 관계없이 같은 폴리곤을 유지합니다.
          const polygon = new kakao.maps.Polygon({
            map,
            path: paths,
            strokeWeight: 2,
            strokeColor: "#00b8a9",
            strokeOpacity: 0.85,
            fillColor: score !== undefined ? getColor(score) : "#ffffff",
            fillOpacity: 0.01,
            clickable: true,
            zIndex: 4,
          });
          // 자치구 클릭 / 더블클릭 구분
          // 자치구 클릭 / 더블클릭 감지
          kakao.maps.event.addListener(polygon, "click", () => {
            const now = Date.now();
            const lastClick = lastClickRef.current;
          
            console.log("클릭 감지:", name);
          
            // 같은 자치구를 연속으로 클릭했는지 확인
            if (
              lastClick &&
              lastClick.district === name &&
              now - lastClick.time < 650
            ) {
              lastClickRef.current = null;
          
              console.log("더블클릭 성공:", name);
          
              onDoubleClickRef.current?.(name);
              return;
            }
          
            // 첫 번째 클릭
            lastClickRef.current = {
              district: name,
              time: now,
            };
          
            onClickRef.current?.(name);
          });

          polygons.push(polygon);
        }

        // 자치구별 오버레이는 한 번만 생성 (MultiPolygon 중복 표시 방지)
        // 모든 외곽 좌표로 중심 위치를 계산합니다.
        const labelBounds = new kakao.maps.LatLngBounds();
        for (const rings of polygonGroups) {
          if (rings.length === 0) continue;
          const outerRing = rings[0];
          for (const [lng, lat] of outerRing) {
            labelBounds.extend(new kakao.maps.LatLng(lat, lng));
          }
        }

        // 자치구 이름 표시
        const labelElement = document.createElement("div");
        
        labelElement.className = "district-map-label";
        labelElement.textContent = name;
        
        // 자치구 이름 클릭 가능하도록 설정
        labelElement.style.pointerEvents = "auto";
        labelElement.style.cursor = "pointer";
        
        // 자치구 이름 클릭 시 자치구 선택
        labelElement.addEventListener("click", (event) => {
          event.stopPropagation();
        
          // 기존 MainPage의 자치구 선택 함수 실행
          // 선택한 자치구의 전체 행정동이 보이도록 자동 확대됨
          onClickRef.current?.(name);
        });

        // 자치구 경계의 남서쪽, 북동쪽 좌표 가져오기
        const sw = labelBounds.getSouthWest();
        const ne = labelBounds.getNorthEast();
        
        // 자치구 중심 좌표 계산
        const centerLat = (sw.getLat() + ne.getLat()) / 2;
        const centerLng = (sw.getLng() + ne.getLng()) / 2;
        
        // 자치구 이름 오버레이 생성
        const labelOverlay = new kakao.maps.CustomOverlay({
          map,
          position: new kakao.maps.LatLng(centerLat, centerLng),
          content: labelElement,
          yAnchor: 0.5,
          zIndex: 5,
        });
        
        districtLabels.push(labelOverlay);
      }
      setPolygonsReady(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "행정구역 표시 오류");
    }

    return () => {
      polygons.forEach((polygon) => polygon.setMap(null));
      outsidePolygons.forEach((polygon) => polygon.setMap(null));

      // 자치구 이름 오버레이 제거
      districtLabels.forEach((label) => label.setMap(null));
    };
  }, [map, geoData, data]);

  const isLoading =
    !error && (!mapReady || !geoReady || !polygonsReady || !tilesReady);

  return (
    <div className="seoul-map-container">
      <div ref={mapRef} className="kakao-map" />

      {/* ========================================
          지도 우측 하단 등급 범례
      ======================================== */}
      <div className="map-legend">
        <div className="map-legend-item">
          <span className="legend-color legend-grade1" />
          <span>1등급</span>
        </div>
      
        <div className="map-legend-item">
          <span className="legend-color legend-grade2" />
          <span>2등급</span>
        </div>
      
        <div className="map-legend-item">
          <span className="legend-color legend-grade3" />
          <span>3등급</span>
        </div>
      
        <div className="map-legend-item">
          <span className="legend-color legend-grade4" />
          <span>4등급</span>
        </div>
      
        <div className="map-legend-item">
          <span className="legend-color legend-grade5" />
          <span>5등급</span>
        </div>
      </div>

      {isLoading && (
        <div className="map-loading" role="status" aria-live="polite">
          <div className="map-spinner" />
          <p>서울 지도 불러오는 중...</p>
          <span>지도와 행정구역 데이터를 준비하고 있습니다.</span>
        </div>
      )}

      {error && <div className="map-error">{error}</div>}

      {selectedDistrict && (
        <div className="selected-region-label">
          선택 지역: {selectedDistrict}
        </div>
      )}
    </div>
  );
}
