import React from "react";
import { Composition } from "remotion";
import { ParallaxClip, Beat } from "./ParallaxClip";

const BEATS: Beat[] = ["Finance", "Business", "Politics", "Culture", "GlobalAffairs"];

export const RemotionRoot: React.FC = () => {
  return (
    <>
      {BEATS.map((beat) => (
        <Composition
          key={beat}
          id={`${beat}-Clip`}
          component={ParallaxClip}
          defaultProps={{ beat }}
          durationInFrames={150}
          fps={30}
          width={1440}
          height={1080}
        />
      ))}
    </>
  );
};
