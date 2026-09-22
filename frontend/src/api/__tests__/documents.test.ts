import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { documentsApi } from "../documents";
import { setAuthToken } from "../client";

const fetchMock = vi.fn();

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const DOC = { id: "d1", filename: "notes.bin" };

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  setAuthToken("tok");
});

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
  setAuthToken(null);
});

function mockUploadFlow(putStatus = 200) {
  fetchMock
    .mockResolvedValueOnce(
      json({
        upload_url: "https://storage.example/put?sig=abc",
        storage_key: "k",
        document_id: "d1",
      }),
    )
    .mockResolvedValueOnce(new Response(null, { status: putStatus }))
    .mockResolvedValueOnce(json(DOC));
}

describe("documentsApi.upload", () => {
  it("PUTs the bytes with the SAME content type the pre-signed URL was requested for", async () => {
    mockUploadFlow();
    const file = new File(["hello"], "hello.txt", { type: "text/plain" });
    await documentsApi.upload(file, { workspaceId: "w1", folderId: null });

    const [, requestInit] = fetchMock.mock.calls[0];
    expect(JSON.parse(requestInit.body)).toMatchObject({
      filename: "hello.txt",
      mime_type: "text/plain",
      size_bytes: 5,
      workspace_id: "w1",
    });
    const [putUrl, putInit] = fetchMock.mock.calls[1];
    expect(putUrl).toBe("https://storage.example/put?sig=abc");
    expect(putInit.method).toBe("PUT");
    expect(putInit.headers["Content-Type"]).toBe("text/plain");
    // the storage request must not carry our API credentials
    expect(putInit.headers).not.toHaveProperty("Authorization");
  });

  it("uses application/octet-stream for BOTH requests when the file has no MIME type", async () => {
    mockUploadFlow();
    const file = new File(["x"], "notes.bin"); // type is ""
    await documentsApi.upload(file, {});

    expect(JSON.parse(fetchMock.mock.calls[0][1].body).mime_type).toBe("application/octet-stream");
    expect(fetchMock.mock.calls[1][1].headers["Content-Type"]).toBe("application/octet-stream");
  });

  it("confirms the upload after the storage PUT and returns the document", async () => {
    mockUploadFlow();
    const doc = await documentsApi.upload(new File(["x"], "a.txt", { type: "text/plain" }), {});
    expect(doc).toMatchObject({ id: "d1" });
    expect(String(fetchMock.mock.calls[2][0])).toContain("/documents/d1/confirm-upload");
  });

  it("throws, and does not confirm, when the storage PUT fails", async () => {
    fetchMock
      .mockResolvedValueOnce(
        json({ upload_url: "https://s/x", storage_key: "k", document_id: "d1" }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 403 }));
    await expect(
      documentsApi.upload(new File(["x"], "a.txt", { type: "text/plain" }), {}),
    ).rejects.toThrow("Upload to storage failed");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe("documentsApi trash, restore and versions", () => {
  it("adds a version by sending the document id with the upload request", async () => {
    mockUploadFlow();
    await documentsApi.upload(new File(["x"], "a.txt", { type: "text/plain" }), {
      documentId: "d1",
    });
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({ document_id: "d1" });
  });

  it("lists the trash and restores a document", async () => {
    fetchMock.mockResolvedValueOnce(json({ items: [DOC], page: 1, total: 1 }));
    await documentsApi.trash({ workspace_id: "w1" });
    expect(String(fetchMock.mock.calls[0][0])).toContain("/documents/trash?workspace_id=w1");

    fetchMock.mockResolvedValueOnce(json(DOC));
    await documentsApi.restore("d1");
    expect(String(fetchMock.mock.calls[1][0])).toContain("/documents/d1/restore");
    expect(fetchMock.mock.calls[1][1].method).toBe("POST");
  });

  it("reads the version list and an old version's download url", async () => {
    fetchMock.mockResolvedValueOnce(json([{ version_number: 1 }]));
    expect(await documentsApi.versions("d1")).toEqual([{ version_number: 1 }]);
    fetchMock.mockResolvedValueOnce(json({ download_url: "https://s/x", expires_in: 300 }));
    expect(await documentsApi.getVersionDownloadUrl("d1", 1)).toBe("https://s/x");
    expect(String(fetchMock.mock.calls[1][0])).toContain("/documents/d1/versions/1/download-url");
  });
});
