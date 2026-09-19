/** Pi's native shell prefix: one interpreter, truthful pipeline exit status. */
export function workspaceShellPrefix(python: string): string {
  const quoted = "'" + python.replaceAll('\\', '/').replaceAll("'", "'\"'\"'") + "'";
  return `set -o pipefail\npython() { ${quoted} "$@"; }\npython3() { ${quoted} "$@"; }\npip() { ${quoted} -m pip "$@"; }\npip3() { ${quoted} -m pip "$@"; }`;
}
