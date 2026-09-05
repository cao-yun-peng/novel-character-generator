import { NavLink, Outlet, useLocation } from "react-router-dom";

export default function App() {
  const location = useLocation();
  return (
    <div className="app">
      <header className="app-header">
        <div className="app-title">小说人物外貌证据浏览器</div>
        <div className="app-subtitle">
          只读快照与证据追溯 · 暂定与待复核显式标注 · 查询不触发模型调用
        </div>
        <nav className="app-nav">
          <NavLink to="/" end>
            运行结果集
          </NavLink>
          <NavLink to="/documents">文档库</NavLink>
          <NavLink to="/import">导入原文</NavLink>
          <span className="app-path">{location.pathname}</span>
        </nav>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
