import { useState } from "react";
import type { Project } from "./api";
import ArtifactWindow from "./ArtifactWindow";
import { readPopout } from "./panel/popout";
import DemoPlayer from "./DemoPlayer";
import StartScreen from "./StartScreen";
import NewBuildNotice from "./ui/NewBuildNotice";
import Workbench from "./Workbench";

const POPOUT = readPopout(window.location.search);

export default function App() {
  return (
    <>
      {POPOUT ? <ArtifactWindow popout={POPOUT} /> : <MainApp />}
      <NewBuildNotice />
    </>
  );
}

function MainApp() {
  const [project, setProject] = useState<Project | null>(null);
  const [demo, setDemo] = useState(false);
  if (demo) return <DemoPlayer onExit={() => setDemo(false)} />;
  return project ? (
    <Workbench project={project} onExit={() => setProject(null)} />
  ) : (
    <StartScreen onStart={setProject} onDemo={() => setDemo(true)} />
  );
}
