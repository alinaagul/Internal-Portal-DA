import Sidebar from "./Sidebar";

export default function Layout({ children }) {
  return (
    <div style={{
      display: "flex",
      height: "100vh",
      overflow: "hidden",
      fontFamily: "'Plus Jakarta Sans', 'DM Sans', system-ui, sans-serif",
      background: "#f1f5f9",
    }}>
      <Sidebar />
      <main style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column", minWidth: 0 }}>
        {children}
      </main>
    </div>
  );
}
