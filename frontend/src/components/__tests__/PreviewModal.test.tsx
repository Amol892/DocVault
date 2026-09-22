import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Document } from "@/types";
import { PreviewModal } from "../PreviewModal";

const documentsApi = vi.hoisted(() => ({ getPreviewUrl: vi.fn() }));
vi.mock("@/api/documents", () => ({ documentsApi }));

const DOC = { id: "d1", filename: "plan.pdf" } as Document;

describe("PreviewModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the document inline once the preview url loads", async () => {
    documentsApi.getPreviewUrl.mockResolvedValue("https://storage.example/inline");
    render(<PreviewModal document={DOC} onClose={vi.fn()} />);
    expect(documentsApi.getPreviewUrl).toHaveBeenCalledWith("d1");
    const frame = await screen.findByTitle("plan.pdf");
    expect(frame).toHaveAttribute("src", "https://storage.example/inline");
  });

  it("shows the server's reason when a type can't be previewed", async () => {
    documentsApi.getPreviewUrl.mockRejectedValue(new Error("This file type can't be previewed."));
    render(<PreviewModal document={DOC} onClose={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("can't be previewed");
  });
});
