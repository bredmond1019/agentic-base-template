import * as fs from 'fs';
import * as path from 'path';

// Parse arguments
const args = process.argv.slice(2);
if (args.length < 1) {
  console.error('Usage: tsx compute-waves.ts <spec-slug>');
  process.exit(1);
}
const blockId = args[0];
const tasksFile = `planning/tasks/${blockId}/tasks.md`;
const breakdownFile = `planning/tasks/${blockId}/breakdown.md`;
const planFile = `planning/tasks/${blockId}/execution-plan.json`;

export function computeWaves(taskMap: any, additiveSet: Set<string>) {
  const nums = Object.keys(taskMap).map(Number).sort((a, b) => a - b);
  const mustFollow = new Map(nums.map(n => [n, new Set()]));

  // logical dependency edges
  for (const n of nums) {
    for (const d of (taskMap[n].dependsOn || [])) {
      if (taskMap[d]) mustFollow.get(n)!.add(d);
    }
  }
  // conflict edges: two tasks editing the same EXCLUSIVE file are serialized (lower number first)
  for (let i = 0; i < nums.length; i++) {
    for (let j = i + 1; j < nums.length; j++) {
      const a = nums[i], b = nums[j];
      const modA = new Set(taskMap[a].filesModified || []);
      const clash = (taskMap[b].filesModified || []).some((f: string) => modA.has(f) && !additiveSet.has(f));
      if (clash) mustFollow.get(b)!.add(a);
    }
  }

  const remaining = new Set(nums);
  const waves = [];
  while (remaining.size) {
    const layer = [...remaining].filter(n => [...mustFollow.get(n)!].every(d => !remaining.has(d)));
    if (!layer.length) throw new Error(`Dependency cycle among tasks: ${[...remaining].join(', ')}`);
    layer.sort((a, b) => a - b);
    waves.push({
      label: `Wave ${waves.length + 1}`,
      parallel: layer.length > 1,
      tasks: layer,
      mergeOrder: [...layer].sort((a, b) => a - b)
    });
    layer.forEach(n => remaining.delete(n));
  }
  return waves;
}

function parseTasks(tasksContent: string) {
  const taskRegex = /###\s+(?:Task\s+)?(\d+)[\.\s—]+([^\n]+)/gi;
  const tasks: any = {};
  const nums: number[] = [];

  let match;
  const matches: { num: number; title: string; index: number }[] = [];
  while ((match = taskRegex.exec(tasksContent)) !== null) {
    matches.push({
      num: parseInt(match[1], 10),
      title: match[2].trim(),
      index: match.index
    });
  }

  for (let i = 0; i < matches.length; i++) {
    const current = matches[i];
    const nextIndex = i + 1 < matches.length ? matches[i + 1].index : tasksContent.length;
    const body = tasksContent.slice(current.index, nextIndex);

    // Extract files from backticks
    const filesCreated: string[] = [];
    const filesModified: string[] = [];
    
    // Simple heuristic to extract files
    const fileRegex = /`([^`]+)`/g;
    let fileMatch;
    const lines = body.split('\n');
    for (const line of lines) {
      const isCreate = /creat|new|writ|draft|generat/i.test(line);
      const isModify = /modif|edit|updat|fix|chang|add/i.test(line);
      
      while ((fileMatch = fileRegex.exec(line)) !== null) {
        const file = fileMatch[1].trim();
        // Check if it looks like a path or file
        if (file.includes('.') || file.includes('/')) {
          // Ignore spec/planning metadata files
          if (
            file === 'tasks.md' ||
            file === 'breakdown.md' ||
            file === 'execution-plan.json' ||
            file.startsWith('planning/tasks/') ||
            file.includes('/reports/')
          ) {
            continue;
          }
          if (isCreate && !isModify) {
            if (!filesCreated.includes(file)) filesCreated.push(file);
          } else {
            if (!filesModified.includes(file)) filesModified.push(file);
          }
        }
      }
    }

    // Extract dependsOn
    const dependsOn: number[] = [];
    // 1. Explicit depends on mentions
    const depRegex = /(?:depends\s+on\s+task|after\s+task|following\s+task|task\s+(\d+)\s+must|task\s+(\d+)\s+complete)/gi;
    let depMatch;
    while ((depMatch = depRegex.exec(body)) !== null) {
      const depNum = parseInt(depMatch[1] || depMatch[2], 10);
      if (depNum && depNum !== current.num && !dependsOn.includes(depNum)) {
        dependsOn.push(depNum);
      }
    }

    // 2. Wave mentions: e.g. "wave 2" or "(wave 2)"
    const waveMatch = body.match(/wave\s+(\d+)/i) || current.title.match(/wave\s+(\d+)/i);
    let waveNum = waveMatch ? parseInt(waveMatch[1], 10) : null;

    tasks[current.num] = {
      num: current.num,
      title: current.title,
      dependsOn,
      filesCreated,
      filesModified,
      waveNum,
      evidence: `Parsed from tasks.md heading and body`
    };
    nums.push(current.num);
  }

  // Post-process dependsOn based on wave numbers or sequential defaults
  for (const num of nums) {
    const task = tasks[num];
    
    // If waveNum is specified, depend on tasks in the previous wave
    if (task.waveNum !== null && task.waveNum > 1) {
      for (const otherNum of nums) {
        const other = tasks[otherNum];
        if (other.waveNum !== null && other.waveNum === task.waveNum - 1) {
          if (!task.dependsOn.includes(otherNum)) {
            task.dependsOn.push(otherNum);
          }
        }
      }
    }

    // Check if task reads/modifies files created by other tasks
    for (const otherNum of nums) {
      if (otherNum === num) continue;
      const other = tasks[otherNum];
      const sharedFiles = task.filesModified.filter((f: string) => other.filesCreated.includes(f));
      if (sharedFiles.length > 0) {
        if (!task.dependsOn.includes(otherNum)) {
          task.dependsOn.push(otherNum);
        }
      }
    }

    // Default to depending on the immediate predecessor (sequential default)
    // if no explicit wave is specified for this task.
    if (num > 1 && task.waveNum === null) {
      const pred = num - 1;
      if (tasks[pred] && !task.dependsOn.includes(pred)) {
        task.dependsOn.push(pred);
      }
    }
  }

  // Clean up helper attributes like waveNum before returning
  for (const num of nums) {
    delete tasks[num].waveNum;
  }

  return tasks;
}

if (!fs.existsSync(tasksFile)) {
  console.error(`Tasks file not found: ${tasksFile}`);
  process.exit(1);
}

const tasksContent = fs.readFileSync(tasksFile, 'utf8');
const tasks = parseTasks(tasksContent);
const additiveSet = new Set<string>(); // Additive files can be configured or parsed if needed
const waves = computeWaves(tasks, additiveSet);

const plan = {
  blockId,
  additiveFiles: [],
  tasks,
  waves
};

fs.mkdirSync(path.dirname(planFile), { recursive: true });
fs.writeFileSync(planFile, JSON.stringify(plan, null, 2));
console.log(`execution-plan.json written to ${planFile}`);
