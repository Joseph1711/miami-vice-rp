export interface DiagnosticIssue {
  id: string;
  title: string;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM';
  category: 'discord.py' | 'asyncio' | 'database' | 'datetime';
  summary: string;
  description: string;
  rootCause: string;
  consequence: string;
  affectedFiles: string[];
}

export interface FilePatch {
  filePath: string;
  description: string;
  changesSummary: string[];
  beforeCode: string;
  afterCode: string;
  diff: string;
}

export interface SimulatedCommand {
  command: string;
  description: string;
  params?: string;
  beforeBehavior: {
    state: 'infinite_loading' | 'silent_crash';
    log: string;
    discordStatus: string;
    timeElapsed: string;
  };
  afterBehavior: {
    state: 'success' | 'handled_error';
    log: string;
    discordStatus: string;
    timeElapsed: string;
    embedTitle: string;
    embedContent: string;
  };
}
