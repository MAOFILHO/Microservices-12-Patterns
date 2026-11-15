import { Route, Routes } from "react-router-dom";
import NavBar from "./components/NavBar";
import Home from "./pages/Home";
import Shop from "./pages/Shop";
import Patterns from "./pages/Patterns";
import PatternPage from "./pages/PatternPage";

export default function App() {
  return (
    <div className="app-shell">
      <NavBar />
      <main className="page">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/shop" element={<Shop />} />
          <Route path="/patterns" element={<Patterns />} />
          <Route path="/patterns/:slug" element={<PatternPage />} />
        </Routes>
      </main>
    </div>
  );
}
