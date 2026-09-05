import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import App from "./App";
import RunListPage from "./pages/RunListPage";
import CharacterListPage from "./pages/CharacterListPage";
import CharacterDetailPage from "./pages/CharacterDetailPage";
import ReviewsPage from "./pages/ReviewsPage";
import DocumentListPage from "./pages/DocumentListPage";
import DocumentImportPage from "./pages/DocumentImportPage";
import DocumentDetailPage from "./pages/DocumentDetailPage";
import JobDetailPage from "./pages/JobDetailPage";
import "./styles.css";

const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <RunListPage /> },
      { path: "import", element: <DocumentImportPage /> },
      { path: "documents", element: <DocumentListPage /> },
      { path: "documents/:documentId", element: <DocumentDetailPage /> },
      { path: "jobs/:jobId", element: <JobDetailPage /> },
      { path: "runs/:runId", element: <CharacterListPage /> },
      { path: "runs/:runId/characters/:characterId", element: <CharacterDetailPage /> },
      { path: "runs/:runId/reviews", element: <ReviewsPage /> },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
