/**
 * Entry-point detection for the geo-asset command-line scripts.
 *
 * True when the module at `metaUrl` is the script Node was started with. Both sides
 * are compared as file URLs of the real path, so launching through a symlink or from
 * a directory whose name needs URL escaping (spaces, non-ASCII) still runs `main()`.
 */
import { realpathSync } from "node:fs";
import { pathToFileURL } from "node:url";

export function isMainModule(metaUrl, argv1 = process.argv[1]) {
  if (!argv1) return false;
  try {
    return pathToFileURL(realpathSync(argv1)).href === metaUrl;
  } catch {
    return false;
  }
}
