import {
  isExcludedPath,
  relativeSkillPath,
  type SkillFile,
} from "@/lib/contentHash";

/**
 * Turning what the browser gives us into the file set the spec hashes.
 *
 * The result always lists what was left out as well as what went in. A hash is
 * only meaningful next to the exact set of files it covers (the spec records a
 * `files_note` on every vector for the same reason), so the page shows both.
 */
export interface PackagedFiles {
  files: SkillFile[];
  excluded: string[];
}

async function toSkillFile(file: File, path: string): Promise<SkillFile> {
  return { path, raw: new Uint8Array(await file.arrayBuffer()) };
}

function partition(entries: Array<{ file: File; path: string }>): {
  kept: Array<{ file: File; path: string }>;
  excluded: string[];
} {
  const kept: Array<{ file: File; path: string }> = [];
  const excluded: string[] = [];
  for (const entry of entries) {
    if (isExcludedPath(entry.path)) excluded.push(entry.path);
    else kept.push(entry);
  }
  return { kept, excluded };
}

/** From an `<input type="file">`, with or without `webkitdirectory`. */
export async function packageFileList(list: FileList): Promise<PackagedFiles> {
  const { kept, excluded } = partition(
    Array.from(list, (file) => ({ file, path: relativeSkillPath(file) })),
  );
  return {
    files: await Promise.all(kept.map((e) => toSkillFile(e.file, e.path))),
    excluded,
  };
}

function readEntries(
  reader: FileSystemDirectoryReader,
): Promise<FileSystemEntry[]> {
  return new Promise((resolve, reject) => reader.readEntries(resolve, reject));
}

function entryFile(entry: FileSystemFileEntry): Promise<File> {
  return new Promise((resolve, reject) => entry.file(resolve, reject));
}

async function walk(
  entry: FileSystemEntry,
  prefix: string,
  out: Array<{ file: File; path: string }>,
): Promise<void> {
  const path = prefix ? `${prefix}/${entry.name}` : entry.name;
  if (entry.isFile) {
    out.push({ file: await entryFile(entry as FileSystemFileEntry), path });
    return;
  }
  if (entry.isDirectory) {
    const reader = (entry as FileSystemDirectoryEntry).createReader();
    // readEntries returns results in batches (100 at a time in Chrome) and
    // signals the end with an empty batch, so one call is not the whole folder.
    for (;;) {
      const batch = await readEntries(reader);
      if (batch.length === 0) break;
      for (const child of batch) await walk(child, path, out);
    }
  }
}

/**
 * From a drop. A single dropped folder is the skill root, so its own name is
 * not part of any path, matching what the folder picker produces. Loose files
 * dropped together are each at the root.
 */
export async function packageDrop(
  items: DataTransferItemList,
): Promise<PackagedFiles> {
  // Entries must be taken synchronously, before the first await: the browser
  // empties the DataTransfer once the drop event handler returns.
  const entries = Array.from(items)
    .map((item) => item.webkitGetAsEntry())
    .filter((entry): entry is FileSystemEntry => entry !== null);

  const collected: Array<{ file: File; path: string }> = [];
  const singleFolder = entries.length === 1 && entries[0].isDirectory;
  if (singleFolder) {
    const reader = (entries[0] as FileSystemDirectoryEntry).createReader();
    for (;;) {
      const batch = await readEntries(reader);
      if (batch.length === 0) break;
      for (const child of batch) await walk(child, "", collected);
    }
  } else {
    for (const entry of entries) await walk(entry, "", collected);
  }

  const { kept, excluded } = partition(collected);
  return {
    files: await Promise.all(kept.map((e) => toSkillFile(e.file, e.path))),
    excluded,
  };
}
