import Link from "next/link";
import SmoothScroll from "@/components/motion/SmoothScroll";
import { HeroVoiceMorph } from "@/components/hero/HeroVoiceMorph";
import { LanguageRail } from "@/components/hero/LanguageRail";
import { PipelineStory } from "@/components/story/PipelineStory";
import { TwoModes } from "@/components/home/TwoModes";
import { MeasuredNumbers } from "@/components/home/MeasuredNumbers";
import { Nav } from "@/components/layout/Nav";
import { Footer } from "@/components/layout/Footer";

export default function Home() {
  return (
    <SmoothScroll>
      <Nav />
      <main>
        <HeroVoiceMorph />
        <LanguageRail />
        <PipelineStory />
        <TwoModes />
        <MeasuredNumbers />
        <section className="mx-auto max-w-6xl px-4 py-16 sm:px-8">
          <p className="text-[1.15rem]">
            Your voice is cloned only with your recorded consent, and you can delete it any time.{" "}
            <Link href="/voices" className="underline underline-offset-4">Manage your voice</Link>
          </p>
        </section>
      </main>
      <Footer />
    </SmoothScroll>
  );
}
