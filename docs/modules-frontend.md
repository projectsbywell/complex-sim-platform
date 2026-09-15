# Module: frontend — User Interface

The `frontend` package contains the React-based web application for
visualizing and interacting with simulations.

## Package Structure

```
frontend/
├── public/
│   └── index.html
├── src/
│   ├── index.tsx
│   ├── App.tsx
│   ├── api/
│   │   ├── client.ts        # Axios/Fetch client
│   │   ├── simulations.ts   # Simulation API hooks
│   │   └── pipeline.ts      # Pipeline API hooks
│   ├── components/
│   │   ├── SimulationCanvas.tsx
│   │   ├── ControlPanel.tsx
│   │   ├── ParameterEditor.tsx
│   │   ├── StateViewer.tsx
│   │   ├── ChartPanel.tsx
│   │   └── Dashboard.tsx
│   ├── hooks/
│   │   ├── useWebSocket.ts
│   │   ├── useSimulation.ts
│   │   └── usePipeline.ts
│   ├── store/
│   │   └── simulationStore.ts  # Zustand/Redux store
│   ├── types/
│   │   └── index.ts
│   └── utils/
│       ├── rendering.ts
│       └── formatters.ts
├── package.json
└── tsconfig.json
```

## Module: SimulationCanvas.tsx

Main visualization component rendering particle systems and fluid grids.

```tsx
import { SimulationCanvas } from './SimulationCanvas';

function App() {
  return (
    <SimulationCanvas
      simulationId="sim_abc123"
      width={800}
      height={600}
      mode="fluid"          // "particle" | "fluid" | "contact"
      showGrid={true}
      showVectors={true}
      colorMap="viridis"
      onStep={(step) => console.log(`Step ${step}`)}
    />
  );
}
```

## Module: ControlPanel.tsx

Interactive controls for simulation parameters.

```tsx
import { ControlPanel } from './ControlPanel';

<ControlPanel
  simulationId="sim_abc123"
  parameters={{
    dt: 0.001,
    damping: 0.99,
    viscosity: 0.1,
    resolution: 256,
  }}
  onParamChange={(key, value) => updateParam(key, value)}
  onPlay={() => startSim()}
  onPause={() => pauseSim()}
  onReset={() => resetSim()}
  speed="normal"          // "slow" | "normal" | "fast" | "turbo"
/>
```

## Module: ParameterEditor.tsx

Form-based parameter editing with validation.

```tsx
import { ParameterEditor } from './ParameterEditor';

<ParameterEditor
  schema={{
    dt: { type: "number", min: 0.0001, max: 0.1, step: 0.001 },
    viscosity: { type: "number", min: 0, max: 5, step: 0.01 },
    n_particles: { type: "integer", min: 10, max: 100000 },
    seed: { type: "integer", default: 42 },
  }}
  values={{ dt: 0.001, viscosity: 0.1, n_particles: 1000, seed: 42 }}
  onChange={(values) => saveParams(values)}
/>
```

## Module: StateViewer.tsx

Real-time display of simulation state, metrics, and diagnostics.

```tsx
import { StateViewer } from './StateViewer';

<StateViewer
  simulationId="sim_abc123"
  showMetrics={true}
  showEnergyChart={true}
  showParticleCount={true}
  showTimestep={true}
  autoRefresh={true}
  refreshInterval={100}  // ms
/>
```

## Module: ChartPanel.tsx

Data visualization for time-series metrics.

```tsx
import { ChartPanel } from './ChartPanel';

<ChartPanel
  simulationId="sim_abc123"
  charts={[
    { type: "line", field: "energy", title: "Energy Over Time" },
    { type: "heatmap", field: "density", title: "Density Field" },
    { type: "bar", field: "particles", title: "Particle Distribution" },
  ]}
  timeRange={{ start: 0, end: 1000 }}
  exportable={true}
/>
```

## WebSocket Hook

```tsx
import { useWebSocket } from './hooks/useWebSocket';

function SimulationDashboard() {
  const { state, send, connected } = useWebSocket("ws://localhost:8000/ws/v1");

  useEffect(() => {
    send({ type: "subscribe", sim_id: "sim_abc123" });
  }, []);

  return (
    <div>
      {connected ? <StateViewer state={state} /> : <ConnectPrompt />}
    </div>
  );
}
```

## API Client

```tsx
// src/api/client.ts
import { apiClient } from './client';

// Simulation endpoints
export const createSimulation = (params) =>
  apiClient.post('/api/v1/simulations', params);

export const getSimulation = (id) =>
  apiClient.get(`/api/v1/simulations/${id}`);

export const startSimulation = (id) =>
  apiClient.post(`/api/v1/simulations/${id}/start`);

// Pipeline endpoints
export const runPipeline = (config) =>
  apiClient.post('/api/v1/pipeline/run', config);

export const getPipelineResults = (id) =>
  apiClient.get(`/api/v1/pipeline/results/${id}`);
```

## State Management (Zustand)

```tsx
// src/store/simulationStore.ts
import { create } from 'zustand';

interface SimulationState {
  simulations: Map<string, SimulationData>;
  activeSimulation: string | null;
  isPlaying: boolean;
  speed: 'slow' | 'normal' | 'fast' | 'turbo';
  setSimulations: (sims) => void;
  setActive: (id) => void;
  togglePlay: () => void;
  setSpeed: (speed) => void;
}

const useSimulationStore = create<SimulationState>((set) => ({
  simulations: new Map(),
  activeSimulation: null,
  isPlaying: false,
  speed: 'normal',
  setSimulations: (sims) => set({ simulations: sims }),
  setActive: (id) => set({ activeSimulation: id }),
  togglePlay: () => set((s) => ({ isPlaying: !s.isPlaying })),
  setSpeed: (speed) => set({ speed }),
}));
```
