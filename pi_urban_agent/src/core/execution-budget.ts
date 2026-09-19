/** Execution ceilings are independent from the model's context-window budget. */
export function executionBudget(env:NodeJS.ProcessEnv=process.env){
 const read=(key:string,fallback:number)=>{const n=Number(env[key]??fallback);if(!Number.isSafeInteger(n)||n<1)throw Error(`${key} must be a positive integer`);return n;};
 return {requestsPerTurn:read('URBAN_TURN_REQUEST_LIMIT',64),toolCallsPerTurn:read('URBAN_TOOL_CALL_BUDGET',32),consecutiveToolErrors:read('URBAN_TOOL_ERROR_BUDGET',4)};
}
