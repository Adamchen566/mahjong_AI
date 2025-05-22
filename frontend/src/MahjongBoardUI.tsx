import { useEffect, useState } from "react";

// 定义类型
type Tile = {
  suit: string;
  value: number | string;
};

interface HandMap {
  [key: string]: Tile[];
}

export default function MahjongBoardUI() {
  const [hands, setHands] = useState<HandMap>({});
  const [wall, setWall] = useState<Tile[]>([]);

  useEffect(() => {
    fetch("/api/debug_hands")
      .then((res) => res.json())
      .then((data) => {
        setHands(data.hands || {});
        setWall(data.wall || []);
      })
      .catch((err) => {
        console.error("获取失败：", err);
      });
  }, []);

  const tileImage = (tile: Tile): string => {
    const suit = tile.suit.toLowerCase();
    const value = tile.value.toString();

    if (suit === "man") return `/assets/tiles/man${value}.png`;
    if (suit === "pin") return `/assets/tiles/pin${value}.png`;
    if (suit === "sou") return `/assets/tiles/sou${value}.png`;
    if (suit === "wind") {
      const windMap: Record<string, string> = {
        east: "wind1",
        south: "wind2",
        west: "wind3",
        north: "wind4"
      };
      return `/assets/tiles/${windMap[value] || "pin1"}.png`;
    }
    if (suit === "dragon") {
      const dragonMap: Record<string, string> = {
        green: "dragon1",
        red: "dragon2",
        white: "dragon3"
      };
      return `/assets/tiles/${dragonMap[value] || "dragon2"}.png`;
    }
    if (suit === "flower") return `/assets/tiles/flower${value}.png`;

    return "";
  };

  const renderHandRow = (label: string, tiles: Tile[] = []) => (
    <div className="flex items-center mb-4">
      <div className="w-20 text-white font-bold text-right mr-2">{label}</div>
      <div className="flex gap-1 bg-white/10 p-1 rounded">
        {tiles.map((tile, i) => (
          <img
            key={i}
            src={tileImage(tile)}
            alt={`${tile.suit}${tile.value}`}
            className="w-10 h-14 border border-white bg-yellow-300 shadow"
          />
        ))}
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-green-700 p-6 text-sm">
      <div className="max-w-5xl mx-auto">
        {renderHandRow("对家 南", hands?.SOUTH || [])}
        {renderHandRow("上家 西", hands?.WEST || [])}
        {renderHandRow("下家 北", hands?.NORTH || [])}
        {renderHandRow("自己 东", hands?.EAST || [])}

        <div className="mt-8">
          <div className="text-white font-bold mb-2">牌墙（剩余 {wall.length} 张）</div>
          <div className="flex flex-wrap gap-1 bg-white/10 p-2 rounded max-h-28 overflow-y-auto">
            {wall.map((tile, i) => (
              <img
                key={i}
                src={tileImage(tile)}
                alt={`${tile.value}_${tile.suit}`}
                className="w-6 h-9"
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}