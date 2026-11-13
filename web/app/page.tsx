import { Shell } from "@/components/layout/Shell";
import { Hero } from "@/components/home/Hero";
import { MeasuredNumbers } from "@/components/home/MeasuredNumbers";
import { MicTry } from "@/components/home/MicTry";
import { PipelineStory } from "@/components/home/PipelineStory";
import { Products } from "@/components/home/Products";
import { Reveals } from "@/components/home/Reveals";
import { FinalCTA, ScriptMarquee, Trust } from "@/components/home/Sections";

export default function Home() {
  return (
    <Shell aura="full">
      <Hero />
      <ScriptMarquee />
      <Products />
      <PipelineStory />
      <MicTry />
      <MeasuredNumbers />
      <Trust />
      <FinalCTA />
      <Reveals />
    </Shell>
  );
}
