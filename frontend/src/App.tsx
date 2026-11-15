import { Route, Routes } from "react-router-dom";
import NavBar from "./components/NavBar";
import Home from "./pages/Home";
import Shop from "./pages/Shop";
import Patterns from "./pages/Patterns";

export default function App() {
  return (
    <div className="app-shell">
      <NavBar />
      <main className="page">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/shop" element={<Shop />} />
          <Route path="/patterns" element={<Patterns />} />
        </Routes>
      </main>
    </div>
  );
}
