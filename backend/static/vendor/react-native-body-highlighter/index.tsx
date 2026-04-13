import React, { memo, useCallback } from "react";
import { Path } from "react-native-svg";
import differenceWith from "ramda/src/differenceWith";

import { bodyFront } from "./assets/bodyFront";
import { bodyBack } from "./assets/bodyBack";
import { SvgMaleWrapper } from "./components/SvgMaleWrapper";
import { bodyFemaleFront } from "./assets/bodyFemaleFront";
import { bodyFemaleBack } from "./assets/bodyFemaleBack";
import { SvgFemaleWrapper } from "./components/SvgFemaleWrapper";

export type Slug =
| "abs-upper"
| "abs-lower"
| "adductors-left-front"
| "adductors-right-front"
| "adductors-left-back"
| "adductors-right-back"
| "ankles-left-front"
| "ankles-right-front"
| "ankles-left-back"
| "ankles-right-back"
| "biceps-left"
| "biceps-right"
| "calves-left-front"
| "calves-right-front"
| "calves-left-back"
| "calves-right-back"
| "chest-left"
| "chest-right"
| "deltoids-left-front"
| "deltoids-right-front"
| "deltoids-left-back"
| "deltoids-right-back"
| "feet-right-front"
| "feet-left-front"
| "feet-right-back"
| "feet-left-back"
| "forearm-left-front"
| "forearm-right-front"
| "forearm-left-back"
| "forearm-right-back"
| "gluteal-left"
| "gluteal-right"
| "hamstring-left"
| "hamstring-right"
| "hands-left-front"
| "hands-right-front"
| "hands-left-back"
| "hands-right-back"
| "head-front"
| "head-back"
| "knees-left"
| "knees-right"
| "lower-back-left"
| "lower-back-right"
| "hips-left"
| "hips-right"
| "neck-left-front"
| "neck-right-front"
| "neck-left-back"
| "neck-right-back"
| "obliques-left"
| "obliques-right"
| "quadriceps-left"
| "quadriceps-right"
| "tibialis-left"
| "tibialis-right"
| "trapezius-left-front"
| "trapezius-right-front"
| "trapezius-left-back"
| "trapezius-right-back"
| "triceps-left-front"
| "triceps-right-front"
| "triceps-left-back"
| "triceps-right-back"
| "upper-back-left"
| "upper-back-right";

export interface BodyPart {
  intensity?: number;
  color: string;
  slug: Slug;
  pathArray?: string[];
}

type Props = {
  colors: ReadonlyArray<string>;
  data: ReadonlyArray<BodyPart>;
  scale: number;
  frontOnly: boolean;
  backOnly: boolean;
  side: "front" | "back";
  gender?: "male" | "female";
  onBodyPartPress: (b: BodyPart) => void;
};

const comparison = (a: BodyPart, b: BodyPart) => a.slug === b.slug;

const Body = ({
  data,
  gender = "male",
  scale = 1,
  colors=  ["#0984e3", "#74b9ff"],
  zoomOnPress = false,
  side = "front",
  onBodyPartPress,
}: Props) => {
  const mergedBodyParts = useCallback(
    (dataSource: ReadonlyArray<BodyPart>) => {
      const innerData = data
        .map((d) => {
          return dataSource.find((t) => {
            return (t.slug === d.slug)
          });
        })
        .filter(Boolean);

      const coloredBodyParts = innerData.map((d) => {
        const bodyPart = data.find((e) => e.slug === d?.slug);
        let colorIntensity = 1;
        if (bodyPart?.intensity) colorIntensity = bodyPart.intensity;
        return { ...d, color: colors[colorIntensity - 1] };
      });

      const formattedBodyParts = differenceWith(comparison, dataSource, data);

      return [...formattedBodyParts, ...coloredBodyParts];
    },
    [data, colors]
  );

  const getColorToFill = (bodyPart: BodyPart) => {
    let color;
    if (bodyPart.intensity) color = colors[bodyPart.intensity];
    else color = bodyPart.color;
    return color;
  };

  const renderBodySvg = (data: ReadonlyArray<BodyPart>) => {
    const SvgWrapper = gender === "male" ? SvgMaleWrapper : SvgFemaleWrapper;
    return (
      <SvgWrapper side={side} scale={scale}>
        {mergedBodyParts(data).map((bodyPart: BodyPart) => {
          if (bodyPart.pathArray) {
            return bodyPart.pathArray.map((path: string) => {
              return (
                <Path
                  key={path}
                  onPress={() => onBodyPartPress?.(bodyPart)}
                  id={bodyPart.slug}
                  fill={getColorToFill(bodyPart)}
                  d={path}
                />
              );
            });
          }
        })}
      </SvgWrapper>
    );
  };

  if (gender === "female") {
    return renderBodySvg(side === "front" ? bodyFemaleFront : bodyFemaleBack);
  }

  return renderBodySvg(side === "front" ? bodyFront : bodyBack);
};

export default memo(Body);
