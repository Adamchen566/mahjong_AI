/** 关于这个项目: 上半部分讲做成了什么,下半部分留给想看技术细节的人。 */
export function About({ onClose, onWatch, onLadder }: { onClose: () => void; onWatch: () => void; onLadder: () => void }) {
  return (
    <main className="lobby">
      <article className="lobby-card lobby-wide about">
        <h1>一副麻将,和一个自己练出来的对手</h1>
        <p className="lobby-sub">
          这是一个能在浏览器里打的四川麻将(血战到底),加上一个从零训练的 AI。规则、界面、训练、评估都是一个人做的。
          AI 先模仿一个按规则写的程序,再靠自己和自己打了 897 万局,最后明显强过它的老师。
        </p>

        <table className="records about-facts">
          <tbody>
            <tr>
              <th scope="row">能玩</th>
              <td>你和三个电脑打完整的一局:换三张、定缺、碰、杠、胡、结算,连打多局,每局自动存牌谱</td>
            </tr>
            <tr>
              <th scope="row">AI 有多强</th>
              <td>和三个规则型程序同桌打 1 万局,平均每局多赢 1.38 分(95% 置信区间 1.23 到 1.53)</td>
            </tr>
            <tr>
              <th scope="row">练了多久</th>
              <td>一张家用显卡(RTX 4060 Ti)上 12 小时,897 万局</td>
            </tr>
            <tr>
              <th scope="row">反应多快</th>
              <td>不用显卡,出一手牌不到 1 毫秒</td>
            </tr>
            <tr>
              <th scope="row">公平</th>
              <td>AI 只看得到自己的牌,这一点有自动化测试守着;给你的提示也一样</td>
            </tr>
          </tbody>
        </table>

        <div className="lobby-buttons">
          <button className="btn btn-primary" onClick={onWatch}>
            看四个电脑对打
          </button>
          <button className="btn" onClick={onLadder}>
            看各个版本的成绩
          </button>
          <button className="btn btn-ghost" onClick={onClose}>
            回到开始页
          </button>
        </div>

        <h2>在软件里能看到什么</h2>
        <ul className="about-list">
          <li>
            <b>它在想什么</b>打开提示,手牌上方的蓝条是模型打每一张牌的把握;回放时有一张图,画出它预计四家各自能得多少分。
          </li>
          <li>
            <b>牌理</b>现在几向听、进哪些牌、各剩几张;听牌时列出能胡的牌和番数。这部分是规则算的,不靠模型。
          </li>
          <li>
            <b>观战</b>四个座位各放一种电脑,牌全部摊开,自动一局接一局地打,可以暂停、调速、换视角。
          </li>
          <li>
            <b>报牌</b>四个座位各有一个声音,打出什么牌就报什么。
          </li>
        </ul>

        <h2>怎么做出来的</h2>
        <ol className="about-steps">
          <li>
            <b>规则引擎</b>纯 Python,没有界面,给定种子完全可复现。换三张、定缺、十几种番型、查花猪、查大叫、退税都有,逐条有测试。
          </li>
          <li>
            <b>规则型程序</b>算向听数和进张,作为第一个像样的对手,也是后面的老师和标尺。
          </li>
          <li>
            <b>训练环境</b>把一个座位看到的局面编码成 71 × 27 的数组;12 个进程并行对局,每秒五万多个决定。
          </li>
          <li>
            <b>模仿学习</b>让一个 178 万参数的残差网络学规则型程序的选择,97.9% 的局面选得一样,实力持平。
          </li>
          <li>
            <b>自我对弈</b>用 PPO 让它和自己的历史版本对打。训练时价值网络可以看全场的牌,出牌的那一路看不到。
          </li>
          <li>
            <b>评估</b>同一副牌打四次,待测的一方轮流坐四个座位,抵消发牌的运气;用没见过的牌确认成绩。
          </li>
          <li>
            <b>入座</b>模型导出成 6 MB 的 ONNX 文件,对局软件用 CPU 推理,不需要装深度学习框架。
          </li>
        </ol>

        <h2>还做不到的</h2>
        <ul className="about-list">
          <li>
            <b>不会防守</b>它的分数全靠进攻。别人听牌时它照样打危险牌,点炮率有 50%。
          </li>
          <li>
            <b>只有一种玩法</b>四川麻将的血战到底。呼叫转移、过手胡这些地方规则没有做。
          </li>
          <li>
            <b>单机</b>一个人对三个电脑,没有联机。
          </li>
        </ul>

        <p className="chart-note">
          用到的东西: Python、PyTorch、ONNX Runtime、FastAPI、React 和 TypeScript。189 个自动化测试。代码在{' '}
          <a href="https://github.com/Adamchen566/mahjong_AI" target="_blank" rel="noreferrer">
            github.com/Adamchen566/mahjong_AI
          </a>
          。
        </p>
      </article>
    </main>
  )
}
