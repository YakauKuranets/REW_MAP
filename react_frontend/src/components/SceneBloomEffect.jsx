import React from 'react';
import {
  EffectComposer,
  Bloom,
  Noise,
  Vignette,
  ChromaticAberration,
} from '@react-three/postprocessing';

/**
 * Постобработка сцены:
 * - Bloom на ярких узлах/лучах;
 * - лёгкий digital noise для «мониторной» текстуры;
 * - виньетка для фокуса на центре графа;
 * - микроскопическая хроматическая аберрация по краям.
 */
export default function SceneBloomEffect() {
  return (
    <EffectComposer>
      <Bloom
        luminanceThreshold={0.5}
        luminanceSmoothing={0.9}
        intensity={1.5}
      />
      <Noise opacity={0.03} />
      <Vignette eskil={false} offset={0.1} darkness={1.1} />
      <ChromaticAberration offset={[0.0005, 0.0005]} />
    </EffectComposer>
  );
}
