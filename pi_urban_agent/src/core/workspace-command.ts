/** Conservative command boundary check, not an OS sandbox. */
export function bashBoundaryError(command: unknown): string | undefined {
 if (typeof command !== 'string' || !command.trim()) return 'A nonempty command is required.';
 if (/\b(?:pip3?|python\s+-m\s+pip)\s+install\b/i.test(command)) return 'Do not mutate the evaluation environment. Use only packages listed in WORKSPACE.md and revise the script accordingly.';
 const unsafe=/(^|[;&|]\s*)(cd|pushd|popd)\b|\bfind\s+["']?\/|\bls\s+(?:-[^\s]+\s+)*["']?\/|\/workspace\b|\/testbed\b|(?:^|[\s"'=])(?:[A-Za-z]):[\\/]|(^|[\s"'])\.\.(?:[\\/\s"']|$)|\$HOME\b|%USERPROFILE%/i;
 // Permit literal downward navigation in known workspace folders. This remains
 // a command guard, not a substitute for filesystem sandboxing/symlink checks.
 const checked=command.replace(/(^|[;&|]\s*)cd\s+(?:["']?(?:\.\/)?(?:data|work|outputs)(?:\/[a-zA-Z0-9_-]+)*\/?["']?)(?=\s*(?:[;&|]|$))/g,'$1true');
 if(unsafe.test(checked)) return "Keep commands inside the workspace. Literal cd into data/, work/, outputs/ is allowed; parent traversal, external absolute paths and root scans are not. Prefer workspace-relative paths.";
}
