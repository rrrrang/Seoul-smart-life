/*
 * 사이드바: 활성 메뉴를 표시하고 페이지 전환 이벤트를 부모에게 전달합니다.
 * 안내: 실행 로직은 변경하지 않고 설명 주석만 추가한 버전입니다.
 */
import "../../CSS/Sidebar.css";

type SidebarProps = {
  activeMenu: string;
  onMenuChange: (menu: string) => void;
};

// [메뉴 목록] 그룹 단위로 메뉴를 구성합니다.
const menuGroups = [
  {
    title: "환경 진단",
    menus: [
      "메인",
      "상세분석",
      "지역 비교",
    ],
  },
  {
    title: "설정",
    menus: ["가중치 설정"],
  },
];

// [메뉴 동작] 선택 메뉴에 따라 활성 스타일을 갱신하도록 부모에게 알립니다.
export default function Sidebar({
  activeMenu,
  onMenuChange,
}: SidebarProps) {
  return (
    <aside className="sidebar">
      {/* 로고 */}
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
          <p className="sub-title">맞춤형 주거지역 추천</p>
        </div>
      </div>

      {/* 사이드 메뉴 */}
      <nav className="sidebar-nav" aria-label="주 메뉴">
        {menuGroups.map((group) => (
          <div className="menu-group" key={group.title}>
            <p className="menu-title">{group.title}</p>

            {group.menus.map((menu) => (
              <button
                type="button"
                key={menu}
                className={`menu-item ${
                  activeMenu === menu ? "active" : ""
                }`}
                onClick={() => onMenuChange(menu)}
                aria-current={
                  activeMenu === menu ? "page" : undefined
                }
              >
                {menu}
              </button>
            ))}
          </div>
        ))}
      </nav>
    </aside>
  );
}
