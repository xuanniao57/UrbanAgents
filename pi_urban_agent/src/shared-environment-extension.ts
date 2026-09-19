import type {ExtensionAPI} from '@earendil-works/pi-coding-agent';
export const ENVIRONMENT_ENTRY = `Research workspace: your terminal starts at the workspace root, not /workspace. First read WORKSPACE.md. Read DATA_GUIDE.md for source schemas and ENVIRONMENT.md for installed versions; consult GIS_REFERENCE.md only when needed. Run scripts from the root with python work/script.py; relative data/... and outputs/... paths resolve from the working directory, not the script location. Keep the working directory unchanged. Use the bash tool's timeout parameter, not an external 'timeout ... python' wrapper (which bypasses the Python shell function). No analysis recipe or predefined scales are supplied. These reference files remain available after history compaction.`;
export default function sharedEnvironment(pi:ExtensionAPI){
 pi.on('before_agent_start',e=>({systemPrompt:e.systemPrompt+'\n'+ENVIRONMENT_ENTRY}));
}
