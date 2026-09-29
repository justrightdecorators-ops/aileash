"""
modules/cinema.py  v3.1.0
The sebbi.pro Cinema at /cinema, in two wings.

GOVERNANCE spins the videos in modules/cinemafeed.py on the ring and plays
them in the screening room, as before.

THE 10p WING is the creators' channel. Every video made on Monop Studio
(/create, modules/studio.py) plays here:

  * one tap from TikTok, Instagram, Facebook or YouTube (the creator's link,
    https://sebbi.pro/v/<id>) opens that video on the Wing's TV;
  * the free teaser plays, then 10p unlocks the rest - one tap on Google Pay
    or Apple Pay when there's no credit on the phone yet;
  * a searchable library (video name or creator name), Trending / New /
    Most watched, a spinning ring of screens, likes, comments from people who
    have actually paid to watch, and a Top Creators board;
  * every paid view is sealed into the chain, so the board and each creator's
    earnings link to the block that proves them, with a live ticker;
  * a channel page per creator at https://sebbi.pro/cinema/@<name>.

Page routes (runtime do_GET / do_POST patch):
  GET  /cinema   /cinema/v/<id>   /cinema/@<name>
  GET  /cinema/api/list?q=&sort=trending|new|top&creator=&offset=
  GET  /cinema/api/video?id=&viewer=
  GET  /cinema/api/comments?id=
  GET  /cinema/api/leaders      GET /cinema/api/ticker
  POST /cinema/api/like  {id, viewer}
  POST /cinema/api/comment {id, viewer, name, text}
  POST /cinema/api/flag  {comment}
  GET  /cinema/api/admin?key=&do=hide&comment=      (CREDITS_ADMIN_KEY)
  GET  /x/cinema/status  arms the routes after a deploy
"""

import base64
import gzip
import hashlib
import hmac
import html
import importlib
import json
import os
import re
import sys
import threading
import time
import urllib.parse
from collections import defaultdict, deque

VERSION = "3.1.0"
PUBLIC = {("GET", "status"), ("GET", "spec")}
SITE = (os.environ.get("HOST") or "https://sebbi.pro").strip().rstrip("/")

VIEWER_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
ID_RE = re.compile(r"^[a-z0-9]{8}$")
CLEAN = re.compile(r"[<>\\\x00-\x08\x0b-\x1f]")
PAGE = 24

_ctx = {}
_st = None
_ready = False
_patched = False
_wins = defaultdict(deque)
_wins_lock = threading.Lock()

_CINEMA_GZ = (
    "H4sIAAAAAAACA8V9XXPjRrbYu34FjFlLhAVCJEV9kUNqZ2bH9mzsmfGMPN57x44KJJokLBKAAZCSTLHKT/uYVCVbN5XKpvJw66by"
    "kOd7q/K4P8W/ID8h55zuBrrxQWlmdyu75REJ9Mfp831On24+/uR3r55d/MPr58YsXcyHj/FfY+4G04HJAhO+M9cbPl6w1DXGMzdO"
    "WDowv734vHlqDnf448BdsIG58tl1FMapaYzDIGUBNLv2vXQ28NjKH7MmfbH9wE99d95Mxu6cDdq27NWc+OlgHK5YXBg2nbEFa47D"
    "eRgrIz9qHbVOWhNs+0mz+eqLZhM+zf3gypjFbDIwZ2kaJb2Dgwl0SJxpGE7nzI38xBmHi4NxknTOJ+7Cn98OXjz9ev/1nN3sfx0G"
    "Ye96Okt/2221+kfw33GrtVts9dYNklKr/kne8iW7TmLAGIt7YZT8bFPbY8c56djQetfzk2ju3g6SazcyjZjNB2aS3s5ZMmMsxdXQ"
    "t+FOLw7DdN1swop6Yq19+taBr1672+nC17Ebe/B10j45bMHXaTiHr+Mz97Q7hq8h9DyZsMMRvhvNl6z36HTitSY4UETjekdnI/q6"
    "WKb41j07dD34CnhkvXg6chudoyNb/ue0LWyKaNoDfBiIDwOxtmcvfXqeRO6Y2dknaJ0guvLWiL09O7lNUrZoLn0bXzcTFvsIBP3t"
    "7eUI3LO/YGE89V2bXm12PluPwptm4v/sB9PeKIyhTROe9BcutAp6rX7keh6+gxVfs9GVnzZTN2rO/OlsDv+lnIt6aQzTRm4MjLTZ"
    "QW63R6F3ux6546tpHC4Drxe7HvLoFP9Cqwabz/0oYYabGketT43Wp/aj9qjd6XboIyePcdz61DIm/g3z5KM+n+8RO2Xe5KSPvNjk"
    "bNJbuXGDo8fqL/ygOWMIYK/dan262UFwnHk4vkrGcTifr1EqJvPwujfzPY8Fmx13zUf2gxlgBlYxWqZpGKzVGbJ3ThpG6yhMQO7C"
    "oJek/vjqtg/PAEs/A0d57KYH7CMYszcBOvVdQFfQ9IFKSW8MCGBx/8cl9JzcNoUE9ojCzRFLrxkL+lM36p1GNxkBQLjHjXYrujH2"
    "DRasGok7YU3AuAsTggJpwvSWZbS70ABb9VXcI98d2Sd2G1jutGPROy8OI9AQc4CkB6wcN9qd6MbKqLylScYmgKBFrw0TJuHc9wxO"
    "AOR0C1A0Apbw1mUCIS9bnHDAdqyHYwqqigYgOVY/ZTdp02PjMHYJyUEYsP71DBDYJDzBg+vYjTZ8HmO0VodAsRVzXHMuAEUBMF0D"
    "IpO1RhdE83F0I18aguxF7LUP7U7LPjwG/B1JDPTazlG2+ArZPrYkt44n3jE7lohDEVgmvbOzM4W8J0g3wCVB3QMNCN9oeBVr42Wc"
    "wHhR6BMDVaBDX4aDK+GTquhBVWX1y09IFcxcD8SiZQAAgBexLlh+W67r8MgqTjMNVzVTcUqUn9RP1Wrb7eNT++Q4mwnWtV64N9za"
    "9c5OkbulfjLcZRrmSorz/3GLCArCGq6Jj0j4pNjJxm2QLpga+eIKBPghrIr0mbMURiGs4yhOhy3KqAQl2K4YkJRuiTGVGcZzdxE1"
    "DkEk7NPVtX10jPKGEpVpM6d1JBePOGupco4N3TjXsWctj01tYZNsYapsYcF0UecjNMeglHuIsn7lwwpl74AT4K0ln3fHI2+sYuyI"
    "aCVpd3Rcoh2MkKTulK3FAjuH2CRicRKxceqvEOstfPSh2lQ8TsPleNZ0x6REIjdo3or5UWH2uqh7uFAB1kYATAxEzVU7eBMuAtHn"
    "8LfPEBJJCmSgPiFjEsaLJrkZvShmQOUVax56MJp7M2f5aO4IdAVoN+ChCVL+U7IZ+FegJx+801Yw1Wy3jjivGs0OKoVtRFe40H7U"
    "dTvusWsVNM8hjlAQwNNKWT8iCQTxNvhS7p2XpNt+dOR23fbY2jKLIuZ8EjDMYPYqkEXmDSyrvgbCT8GKq2h51AJvAly6WlWtLbME"
    "aacaH51OSQnjnBM03Cs/8Uf+3E9vM6eCY06sTNOOJSR0t8HQ7qL5ORV25TRHl+EvpmvBm+Dn9BWfpx+OfgQJwiCgR0FAP0SVBdA5"
    "Z5kwjdAlykdzJqP1R8qZOnMu/4et7czaPuYqquO2u0ctWxBNWZ8zd0d1AtTqxzQnsga5Irm3SvYE0XcsLeoRWtRWwZ5ugUxRcrbm"
    "P511LavC8pZ4kQxP9pC7u36irCyKKxaGCgFh5is7Vv2Bs7I7wLWu8IyVxahGXaIEbIpxQoJfckIyoGqMeFj2DbqtjDc7J3YH/muT"
    "KCPp0B1mcdHFrsKZFM4qF7LSW6p3y04shc7tOlQJR0w1oOR79EsaP1sHsCB8redB7vZnHCj9/869Bkt4nqrzUpAWGZYWaaH6D8fk"
    "2KqgGr7QCCe5OSkTHq1OiWMqCH2aIRJfuoG/4P54tJxD9NZ2uonhBxNMQQDKfnvFbiexu2CJQe/XMMs6UzuHGwXSeBlkqsYPyMUh"
    "ZZShg3tnpxTOAKz5zNAT2C8xuMQqs6tjG+66MoIQtp+LFyrYjd6rEEhwESriu9CFLdaVFOIOQQC+gTvXcINrT8E1la4D96iA79gf"
    "Gk1crUWYWgEptlnc9ilXnu1O2wUReNRy2y00UCWpqrBjR0X5aquxJmdEnRGOW5UWsd0hkV/V+0xEPfLmmkQJUM4HZzqbt0rWvVO2"
    "7jSNk7oQvWvDnR20O+RjSl7vrGYlHzNdGSvfY2GdsdQMYgk4zZQGqesjMNhyi7siRyS2Qx3Q9PyYcT8U2GW5CD7AuqKuIKJsCWeO"
    "twT9J6c1Qf/xvTE/thCrdZJZeK07CFLdHXHqYCvmCVRXOURZm3UBxwZfzgG5KkYQNmMWMTel8MBXEU3poFoHQMJzXCBAjf4lnKpc"
    "zwPI+3ItfDrLKtujlt3u2ocdcBOOMwlDC7FNGA+P6jIyrfszMi1OHkJSmT7yDTih6Rof9NqUG+NSoEae7cMsDSPDuL/KyZGzZgr1"
    "0WQyEXm4mZsIonLMy1TSaZd8EWQQY3b48fFzB+PnI4ifMZCWzGtE9VHqoaPHqYddnkFI3QhR+VApf7g8F/mmZeP/OSdw7d3q52hT"
    "ckLHmTnmiU49GMlBrmQF3AJYZ9yODiEyeyeS74xZ569AOrC43XWOAe1oV4tpiw6mBG915UFaEfmqR8xVI6OnWSDclN5xJdsq2UOa"
    "y3DvN+WVaUaM28dpshXWCsDaHJGjVPrQvUqrpuG/nXn4Jy2RvFKpW+PSC85od1sueod6PFrp9hQ8rQ+M7XCxJ3JxDob46xJkaqJP"
    "RCSifXi1rnQ0s7addtZ2OgtBURWlQ0urtvK0qtgEqPF3CrlYMcPIn+YigFFCp6Uz1HHJVW535dp7gEd3NAfrlTm1R0di4LmPVi0T"
    "2tPJ6LRfEfIDNBjNt0+7IlqK3FwqVBdVstRD3DlpQTSkqQ1ax1bFonJe5CuMinpDpgfghTHrrgtYEoAK5Z0NAZEtgFKRZkd5KYiR"
    "cNPI1LaM48IQBglTyWy1uy05Usmlwnk6VcMYyQI9RyVGLESIGUVPoTOEFExdLgWUFbsUNTlj1KfJdF1QUwphSXUoe1SnXAcnU9xX"
    "9YrhxIbejFyFvc68U3ezk/DFO0SntTJ+h6MymdWnc0ZuwlAZPGAbSslFZrs+LTHBRxrqTkf2h+mCLWSp0u3jcLEASIGwGD1V6OlK"
    "tjgtL4KA8INomdqoNtHDUwOELenEh+37aApKy1xmkocjkZgTCtpHugXY7GRwKexyjLIbM0Ik+F7gSmGASevoTcLxMslWw7+uw2VK"
    "G9CkX+o2hBCxi3Wlz6qmZTRvmVNxvAAvb4tN5sNjs5zY9xNaEotc/WM5UaRO1NWlCudVndYoZqRr+tewqOYI8HHVo3+b+EAAXtrv"
    "U5CUeWFFma8AX7fCqixyTofQfTyrVIrktY2q9yULGlKLi5s3Pdr94lvaIzcW+lH4MDimXB7pUHVh9zHwlv3PD9nVpPTNobar2dmK"
    "OB3uD9u/xHx77HsZHvFLH/9pgsKLML3S5Oog6fHgsoHow3BqboN0gfvfaB8BxHZ7EkNsR5pPMLgbV7g8+NT6kBxmVVaj0n3jAT4y"
    "fl+rSshzhQIow0lnFZmXYrql3fq4JLyc4oO2GYrOQzbIB2e8S/n6v2HCm0PlB2uVVc9E8UQO9boUJRYjCD3MOcyWn4Xt4U0WwlNb"
    "Cpd6nb7SoBnGSIlMmVekvjg84/WWwgm+fF0fZj2TD1W7+QAgPOntusb5yRVxfWoKvRGR3M6FxXOTGatUP12r2gEnOKqiOrELzeJk"
    "/SHS2K3MMc7jhyiQQ6qzmcS8/iBzkipiqrKlv9fE1itfihjmcW/ix0naHM98DMXy4Vr01nBiXs3AhehoC8V51FaiHJ8kSGd8ikbb"
    "ojEz79M7OXY3epOO1sQ7BWweF5ocak0YBK/HIw6w6wSLtSpYEA0XfKiaQB1Xm6Qfw9tcs2N/FqtVIqSHNuKFMdJjoeqtmKzUIevm"
    "PgAirB+06taVhqk7Tz7AlB2S1apzdEU6iwY1PH+13rqR9qEmTds2qGImMXERmQryTgu6jKIe0U1xGlvO0UPig5kbVMXUfFu4ZbQK"
    "SXN9RccPjLm3bh+3D4/Qplbul9jlPX2IzyXg1RE4vvnI9NyhMGipq0aIh60HqOzTMnZO67GjV249GDtKtww5evLilCMHE5R/TVa4"
    "i1lhh/LCXUxQ6jJyLLG0LVHcLSSKjzqlgiZDWKsJVhuXEfwxVriVDViwfoLhH03Dlcbv/FElJz2CGN8BY8cKHZw4DBfFXRaZ5Za7"
    "Kt2/17bWwwuFD6lSuNv2up2sTPjk6FOrUCfbva9OtpNt83Tv3eYR2KnMqeMLw5mmK+EfQyDROOsCj50c0+5Nxc5n2Qup3gztnWUC"
    "9qg96hweHvdlIN+pFz2QvLJTQ1D6tP1c58dnEW+V6qkJTouRaC4YNKQkCS6xJkilwR8cpdZrmNogtTIFc1IMUdtamdDHFd6qS9lS"
    "SFO0chC0whDCvnW26AXsXNYnahbxRK8mIQ/n8QE//vAYCOBHqZHE4/wox48JOE/wmNEZjtXhgTmE9tQQPvBTKrhjN9zZeQxegwGK"
    "NEkGJoiQOdwxHrvyAdVgm+KcCAySsNHIfzwaQsQXPj4YDY2//Jvx7MXL518/eXzgYk9lMCokhnk54gzfg0cXpnwbBubw//6P//C/"
    "MXwwvoOmMBw11Dt8kXUAvYc9/uN/M75A7gzcYMzyPgcw8XBH/OFrwv4pnsrRlog0NQuQYj0xPtMeYumwObz48jmH8MXLL8To0GzW"
    "Hn7npuOZMYkZc6jBJIyNdMaMmCWpAyhuU8NIjoZhjDk8iYxwYjAA/5Y6TUMGXlAau0hmA0wMjjAGPZWGsWO8DGHUOUghxD9GwJgH"
    "URW0AYMbOMZzGiRy0Ynz2bWRMHcO7wFvNMbM9QMbRExMFrEguDX8xAC6rcBOPD6IEAdiQeqyqWbX5Mh7S5+H6musohVv3+BH7SVW"
    "kpqCFuq/+gy8xkYMIj4TKw9M1QbpQ2P9EzzxYUR/+NWLd8/F+CpoyyAf9M0y0CHZ0YFAmeat6dOwTPlnXz55+fL5V2KMWSdr/BJ0"
    "LY4962i9Rrf5eIC4NDGHOcOoSBqnilTIzmlg0BaZMsYMDJY5pD9IzyBg8wK/6yvDjog9Fn8neFxHO1YdCQTRR2xQaCFfA3xU6SG+"
    "wnMcOOGbjHSwDHQ+MhObhy40wT1mz01dXDJ1pLGNwiLFDraYxI1e45fhr//0r8aFGyFnX6NMZWvkQ6g8AGaLd6ZPQJTD4Ve4OWf4"
    "6bnBBVIVwcMhyJ9sfnGTmkOUuWVAp4Wo5WQ5n/OaFsc4EeJYkEKUlApijfxpDsrTFDjoWxoXFSLMUlJm1XSGEA9wgN2lBEgtfyYq"
    "Vgo74oCuP/4fZamof0AJxOA/TkHii/oQEZh/UlCJBDMFhgVrry78dC4Zu4R74O4hmAVq+PRWWoRH2NwFEwSBHH+XcT4+UsCoEAF6"
    "bJQRxFHDybQFs3XdVfzi1i0N8et//RcjhxIfvzSHrQzKDxgyQXmkMUkyP6hvvFBJrTnc2v5f3fby0YndPjy1na5lDt+wBWhyY3HL"
    "+bcgNdV4j6Tw4QcJ8aw7fAVCDfJo4HkrP+WyjgLUlW2UMXADNRvkqTs3VSLniujanc9Zmq1V2+yo6FIanPf/EryyanxV+EviSEVH"
    "lpeaw8/dJAVdAHrl1vj1lz9lawQFNvHjhWO8io0lRiAGpVJHoM2unTrYaMdZrhw/bl/F8As6R2u8hrmBc5+A6su+4Gxk3t3xGJzc"
    "1DEuUOMgDBOQZzDTb8l520voFPGUce/CvQLNQGIPqMd9UtsAbSGMfhgVrT14GrfhMkZN5gFVSblBS2KXhOOB67jEmLIUx/VjrhGJ"
    "xx3jH5Te4BbcJty7QC9iBjRQMVXDcItEaEn8UKWU8g9ixzuTHBJ5uR8srKL8VlJnyYxbg2eiBVf+mbyPnyGWK7RSxq7jL9yUmTob"
    "aqyrJtzMbB4EEJUwxGARC5HC17NwD8SSLBkDIgvdBUblRwgxDD9wqhUy7neLVX5OH6s9ItoK5s3IDTEW6HMF03Q2MDtdMtNjNgvn"
    "oD0GJtEv4N6K3DfmfS/gm9a322oVOr8FVk1gdUBvYDp3BAEqpz3xD+JSDjmsU+HjtwyCh+Fr0H+SkrmBquKS8dc5m1QR6Ss/SVWv"
    "6kAwTY0rS9sKfOQgfEdsX4NXFD8Zh6D4hSBB9BFI7IUgIQ7GRCIKIqmBTq8JI0B+TNlztKCAYB9+6CIxfv3jfyL7mPlpVVwuTRXE"
    "WvFtyW0TrC3bCCONAIseBV6HpzXcro1Km9YaQ/1kGultxLJ3BXagh0J52LnmAL30CKIEQCxp4St2C/ySKhNsNYg/cUNKbcu+i+ab"
    "uqNEOo4jxX9Gr7OJ72PgNYpNtPjyT/9iXIg3JZdMdg3YNTgIf/5fxkt2XduIImOIPv9ofB2SRSH53g4zpvU5zPSp0EgwYp0h47tI"
    "XdQ223G4CGNWw9ZfwytBshKkivBs5ctRCGapjiuHF2B2JC/kjDh8/ebVu+cvjVcvDYyfIZJ68XIbN/LtAEFe/rm6odgMFBIjvtQs"
    "SQ32hLNbDvI+f/XGePbm+ZOLV2/eKuH94fA5BNlcsZMNlTLOrnlgQbH9UAnQjYUf+IvlAmQjwEDGT1F/zEFhgQ2IMEoC3TBmthEh"
    "+6DaSJmbQD9A+oV/dRFe2caLAIPv2F3YxucgeqMwvCIzDXr8YjmCvviFW3j0ZNKZm6IngEdyQOdA/AIGhqCNsBA/FUG+ms1BzgGB"
    "5tFLQZ2B5w5hBCYXEHKhuaoVKyasKRwQQ2AnMIqcDxAkMBYJdkdnR1Oc4EoAwb6+FW5FuY1IMfH8klvI62jpnSxf4UtW5R+H+lsU"
    "n/zthTnU40RMYj0exYoCpXZvKVdTEQ9qbFxn+GiIbUGhWI40bJja0tJchURaVTjPc1YljpaKoLQXzFNZX4Bcvnn55OWz50pG6/Gs"
    "Lbvdf+acX5kiz5rLs+cfcebcHD55ARiWqTwbJYEztziySEm0Ygbtd7E7RZIkEbhSlDdwRXsbyRRwM8TJi6lxmVXgcXylKcwTXtOt"
    "Ca/phyS8dEMQhNdijJfwaUteSNKhZlvlQaYBqC0me46dzOFzHSW//tO/VlgDTc7U9UMXEb3ip6ImyAI2fIuLq7VrZmUycCqTTlPK"
    "OlW0oOy7aPOMPlc2ewD67rOk09cxAyB+/S+/PDB9M31JfKwhdCtBvmIupjGfgjjUpq5FOp/bXtCzwivD3Jk/plKCgx8T9G4uL5++"
    "enVxeZkl9mXf4U5jsgzIEjas9Y6JIS7uBoxTs78DKsF4Ovj921cvnQgvqGp44XiJrrkDQeDzOcOPT29feA0+u+UgIZ9xPN7dmeuN"
    "afV35PDGbxq+tY5ZugRrWTeQb23yDiwZN5KsC4a5wbSRDAYBxJ3nptlLLIeSYmPWOHi/+3ho7v1wMLWz5Yxl17W5a/bMXXcR9U3b"
    "fIyf5yl+HOLHKX7cM/fg40/LkJ7v4fNHh2d9c/N+/MNGhWk6ihqRtY4G0d1dqy9Ai4aDdqt1bv7ln839RnQAnwEV4ee4e9roWL1o"
    "34xMZYxguWgE1joYBMoYAYzBjs8bwQH8ybu3lTV+77R+c2CbprVvLswedTjkHQ7v7XBl9gQCA3U56KWwGBBvrdP4do0EvxqAGXLn"
    "b8GAgYJDAr1I2aJhclvLOwBd/Unjanf34N+/f9L8R7f5c6t5dtn8YX1qH3c3vzlwMJXSuLIssbirzRgVa4NZ680O7m0ZwO8r0x4D"
    "r47GHptMZ/6PV/NFEEY/gfO0XF3f3P7cancOu0fHJ6dnZh9CXrxbwvAHrb7/uH3W9/f3rWR/MH7/tZvOnMkcAq8GfcRNqHDRsD47"
    "PLZ+6O8YuCxtQUnlguzEUmAUYCcbEoF3L55/9/zNIMeVwtSAnt83lhmTThgOsbTXYxd8/h7Eks0kRad7AxQCk5MLW5z1iR2U0Uax"
    "gWetPecyGcR4NUq6TCSjeBtbkVjB4ZdJT7bbAL+qJEYnEkC0R2UgMWIPvZ75+tXbC9OecR+5tzaFCDcvQJuAKJTUyYYu9uqRYkiI"
    "q0CBNkZ3d2uc+//XQhP3tsHmdmqP56A1kHCLwW/gidVfqIppgKrJhGekdl/SXXiYVdhvQL9z0zD34W8PhGazs3PwmdHM/kd+BDm8"
    "uGL1xWcHORRvSEmhb2BjMzsMXoOvxeFxgylYnJa9YvOB0+7aHjAkaTMbQEn/AG8wT+vBX6qbGLz/wR4v40GzDXycTTBaYhkdRgt2"
    "OlsuRtB3BMuOQGcD6/KO+Lb/JI7dW3SOIUwCQuIxiefAlQ7IwryBsDk/LcGFesvmEAmF8RN4aoorIEwrRz3gMgGVgpA1AOEAigGy"
    "/wmFKzwlJKS8j0sMBiSFWEattLCPLTvmb8iza7RbRwf0NXUDLrevXxwElrV/2MIJdHEPSNqFcvI/Vcdd0VLfX/1ge4PMpvAoRZiV"
    "BsS5K9BXnkpvsUp4iDE7aATnanCFExueQ26Bkx3LR28F2I39QwM45PC4dRB85oM+Bf/WMrIT+/8IL2PQ8jeWKUYBTmHxlxdffzUg"
    "IjVWFlgGJNH5npYoBkdjbx8NHb2EZtb+Hjfve8iD+1proLRsTkTXmouJXc97voJ1Y/6LAQwNE7xocPZVWQL6EaMNjyXpkM32MWWX"
    "IwQdyCvQdZyBG8RY76Ed8SQyArEQ6AYWeM+otNOzNrzPRmFX/mT9t2RGwgauD4zeFCSqgQkce1+BfTAYcCBVSMBGRHzxJHfcj7DW"
    "JJT7A5DJPvy3P2iAZDbhk/WZ02pvCLQtLMF7EzuYoLhgEUn6RN5S8TmW2jRwXmvDZwcikW6oIJMoK/HC60AhFog0Qctg1Rha/aHP"
    "VUX+XagMkszaUbGRPqpAwycSDShd3k0+bpPm4aPvc9F1R0nDw2omjjHv5jOnizgTnwqAbbZDtIw0lsxUIfUSyp5UXY/+tRPijF7W"
    "BVQqMq1k082mpK4xSXtd1tRk0bnWfXvx5OK5+PjqzYWSGbS/GZimLbI9+PHV55+DWk5XYFFok9vi3jEVNgxI5+MLHhNaNn6mCFBh"
    "3ZW1xtROY2WnMdb8QhtlB95yeG3UiyAN34Gj0ViP2Mxd+RCYm8kCvOuZaVOmrYdBaJyaG9LFmpUH52QxxXmEAd177C+mhjtPYQEG"
    "zo2wghL5+dbkFUBclawc3hlUiQmBNYvjMMbrYf1EepLf+ems8YqOeDggehCnNWqU7fd7oIu+37PAAZLatvf93mT0/Z6tmGB4hOU8"
    "3+9tLAsUGlAuN+Is/TaeNyLgN+6SAhigD24lKLhnzBpEMqAKNVP8NsUbELhGFNs/LX2WWut3g1U/J3n/q1fP/t3z3w0m7jxhSA3K"
    "Y1qKdhFGz8SKP5MIBnFnVQN+mQU0oWROI6OvrFvYPmi0vQW6NeSgoCMPslHiG1JO8v5b8GygQbaFUXpNyV4+itjE16K2wcpJ8SkO"
    "gnv3+kvzt+b+yhHZrbyJTNlBfL9wD6ANC8ahx7598+JZuIhgQmAMEXxkvZUoxYCgzbw0LaEc0wTUJHlvbAC6EFQGYYnvhxfX01iw"
    "3d0Fc3DnKvsAZuErzLM+A2PQsEDRlyfXWlgYTArMwEx5NUFh9XmCDtFABvuS7HCxlzwgnvOW+lbxQzALyInxMVPKUpUiBZVm+2Zt"
    "DYu5r/hjotNnzgn4NnkyU6X3vukgrKlUFwP5oQ+PsAbZGyDj4zdULsBIlLSGLmBqkFjcxkQDHAG+NiiGjHZ3I4cE2BJ/1XwEGXD0"
    "NkmCd3efIrgpA6Nliion0xIaI+O/1QEC7XvITpmWIqaWzA1IwR3+0a2hLU9kXmljD1dKoZ0J47mRf4CMyc4x0UKD75u7PByE7zw8"
    "rIhqEPB3d3fvoD1ATDAJd4trIU/40p7DacQ8C2X+W/EFniO9bI+f7L6k6mubWIr74QJAsW6Ekkj7V0N5d/eJ59BQEl6A8x3dbZAM"
    "xBv+rf+OSJk/pW/41PW9S5xbeZU96ksph2GRjUXhjVXh2NF9Cqb9CQBEH/FsC+h//D52g0uxU8zRIbf8G1pQyKdao7Li9Ua6tGAu"
    "RiwCOJ+Xs3BxE28yqOm1LKFMSFPw2qCqAQk7Fk8faHYmhywMLkhAstjW4JLjEJ1fTYCyXIJMa9jSDNv46mV43cgo1yBu2t2lPzkr"
    "ARXzKSQhBSxcUMG6oiy6S1SCWoZGmjqubPOM/IsF+De4b6yn+7Vbpo6OLLv4wLKXIKJ7wIVCZ+ybe5ZZYVHBXVTMKcl+JsMoDDwi"
    "EN7G7m72jt346efZe+451Lxs6A6DUWX5CQxufzc7gKOyFwt+IjKmIAaAWtkq9RdsGXm4Z1aIvz7hlNjdzWm0uwtjgE+Lt01eQMfh"
    "oPHu/J2DZXuXCRuHgZfc3Z32Ti0rY4FN3cRUO1mYks/IcVNJd/LYMT2G/vnKnTeq+u/uflLDcHxdcmRv20T34Xxjd1stAAbtflb2"
    "aDlhQLHsQIHr7+DE6VQYtPofY7Zq6IJeKfOyEliVQmXIpBLE2+5MiD24Iv2S6vyH8ut3eJCCGEFzOCtQ9TCHNDPmHKXZqmFFilZV"
    "zRQZKTJRNp7/4KaeWzj6F9OCfZ1XuALaMf4O1HuAQ01OOrejfZ6NHg10H60/qnLDmGf8+uf/bMJL3YUzwit8mHl9YnHAJoQVS/Hg"
    "5UCiYA7dDT+R9fh+YPBSNnOf/u6bWom+A/3xYhhTQp0OdFaVrhcSpEhHAicnzwezdA3zqEKLvhpZZ4p/1KCOY1ZaLDVdWIF4HY3F"
    "6Idns6VXxnua9tr3eujA2Nzd6XFnZ1Ph7YyKznnJBVvf74PxAA+6YSornBjw1p3jxvRlBKEPg4jDBDdghKa7gvbcvcCNpEI/9DBE"
    "CSXe+lCooDTelrhEgwr984xBOIo3cnGXCcDUbXX44l4DTIWp7+5aaqccas9ZsCQBq393Zz4Ll3Mv2EsFPQ3cOTWC8NoxLuJbXlSO"
    "IIxcD7mhzEMl3CvIeRlipW0grjKqHHCj6x9cBayB83KS5rrGppLbAXAnfbi7e7+mNeJxNJ4s75l/+ee202qZxC94Gc/GFm2O1DZH"
    "Spuj1uYHEX3zWmbd7QNIzrGI0pi5KybIi9BlJIU1hZGxpLMLAn9EXCQtRJ9Y7YtFP8a1n84MpR44jPN6YAza3hXCO6wqhVEmE3Gq"
    "SFZdOqaEFuuPLSUhTU+chRvltIlsX8kalbal9/Yb/rkpdrN5Wtrk1W4RJpEih3AHD2Uu2yHooJms3aF7t4a4HtmCFyvzZdzdZT3g"
    "zYSx8z1g8/HcyVrDs8t8TFH8vNfb26P8Nx9dTILwEMmgpahfBoELsgLqrLncVN8DXsWC2wbXMFsz1QpCy/lqPp6a87ux1jdVphhY"
    "qLF/k+WrI/vG4ulS+LaMvqN69obwf4mPby/xp3tuQYq53apjQ+QjXm2MJ4FGDNOfCbAUFiAaKFjPZgw4Dz16FKI4nd/mjFKr2nOj"
    "+uAkJQYILKE0JQVBby/evHj9/PdveepN2eMPkmXMeAl7I1qOuNeIduIatBroFv4Kghl8KffKcQxsI0e1suGVkeQ+onyXO6DKMGrK"
    "UEM+qZVrNE/ieAIp/E+upfW6ViSKJ92UYwi1abeirqIxAdm87yWAPfeTGepIiOvgee5cZ5E43z3X8FY5AIc30Tsi8w4aUjXu7spP"
    "71s/QMCo6Ekunr12p7MpWV2feK3O6tp8EByW64UqMyw2ET2xWYDxDcBJiQc+M3ysD22VtAQtKh4kjjjm8IZvwTTWJOvxbc/84qlp"
    "cydpDN9AL4MrjXWjvbXQ81kxN9dVpu0usG9PgrKxxb7Oa8y6UkqbhFB7/Hzh+nP+nO+RImBsvgA75DAersq8ZhSPBvhGpM5JtBTQ"
    "n3ItYq/1x70otvld4uuq9r01Kque6bGJu5zDIujn3Xom/T4X7u3T4WDzCI8k8EDPAEAwifK1e8WE1ihtzYMIk9MGf3d3320L/VBq"
    "YWEOoa5hPsqE5h7BMNWwkOFt8R8hWPl6AGaJTl7coG56rYjvDPytOjrT8wzsiFx5gRMz7F+KGgm2khz2NT0AtgefYeYG3pw9ofET"
    "Sf1y/QOddUE0OrS5Yq1hNLDbYNWR/BPgHC3PL5opnpeA0sCmjI4D8aMW126CR31Y7iYpTpxhaNMky/EYBjQFE/qDWK7oBckz7R/n"
    "u6UeIBYtVYXkX+K7evEXiONte5GPqCoiZSmQQmhZ1jnfS+58Lyucb8V1fI1JOQjMjDxK++VP4ClBdwHLOXpj2TeHy3nJ56bzUeiL"
    "seDHEMyiJb3pjQAV2VNxjRvL3d2lJJJFVAJk4Nl/cMp0T/mWpbwAVeTz7/eVC+vTeoMHiYdODHAqVe9YYDPyIZDzRY0MhiKopnyQ"
    "4Ev++0cmbaHfKwElNu5wTdCRPKzwa6fEsFmogD/LkMzUg2glVkVW7BR4kXOfXBUhPnuEsl6FMnihlj0BeJENzivEHWlQH1W+Esd3"
    "FJf7IPe4f/3lf1aEnegL3WP96o0emhXwwcJlyrVmQzg6EJrf3fHPFt5VThUEfG8t75Jry9oWuQLQ1l2MuCoDO2IrSaeHRnXbZnlY"
    "XFfYIJMOM3/W13bHCu92drQNhApXuzrlkHVRaKvso+DrD8kqqKkAvk2ipADW+dYJ3zSR2x+jh2x4bCiZqES+4Fc3aBsLc+o0dQAu"
    "+JQOoNNba1140FhT+x7vheFCLxugB/9VCxNwEMmdNgFW5NMpH3WS7KFzHfspwwODDYStgCdNqX2FPyk7DiOfeT3Q1dA807b4uye/"
    "aeSHp+vI+s7iq3un7eplO3g2oh3vBVQTl2JDmQRPRAFKefO2wlexTWiiosfAwbTq4glls7oC8MLOttjD+WTB6B/nit3m3i2+FJq6"
    "YYpD3L/+8mdMAogl//rLf+cnj1LlVOK5cYFpAPDtQKRHDIyQR1kGxW/W9ZnH0EUAhofZexwIW/B+Dbd7IqnqaUTlIIKxepHuJcYU"
    "Js2BQ8CUBFW6EiM8SSGGAZuJHko85m+odkNuD24rduBhlZbQxXpAkYEs2OtKjceBQFNqvPWneOiW6ye8aUocd1JVlSqJNGsYZAko"
    "5Fk6VURUDQPuMWPilOmbm+LXY5KGiVdwAVnWsutFMZzXDyDhMe0S/clFFgeR9N7K/v672v39d2o9R3YYaUsZgpaA6uNyKlMG2e4b"
    "/dhHoY387Q9Tapm1Nk4hYV83lGymjMY1R76KCgGUyWig5cFn2aaxVsNLWezwiujCT3sXOS+8OufM1+MhCj+IXdUqqyzhpejYlk5j"
    "W87KnS/ZoPjg7m6bFqIT2qiCzOqqp3wPnLjS9wYoxP1ypYBsyIsFfO/ewoC8eAEHnqPHIYa4u3svMqPi7LzOPHNRq3suP+w35Kfh"
    "2dm5uc8zimZ+gB9xysejQ9xq7lIZDBOY40Weuuvtle9VIO9DEPiWTjnyUtlr8Ic/n7vTpKHnlceL/NSIoY03XuCJIJHfHBMdKPU4"
    "EqdY5Qt3GvKUJJ38i7LniBF6EenHhakKb4y1Gnt4Twf+YnvhtM+eAp8C9/q+PKVEXl2e8j2f/wc1XznCJH1VvrLsIk0ADLAYAr29"
    "/VGWzRxvSvtnfGHg2GyEu8eP+9cayKAkFg5YiUXDsknN8jsJ9DdkSdPcwt137oMkyQ5KdQ8SMj1gqECAWHltIIAT9ALhblWZ0arJ"
    "9D0pqpUQLdUlY16E7BpdgkA7Y4i1yaCO7A2TfsyCW6aJNcnq+fualCUsTp94P7p4BA7FrWG6k5TFIzb1A9MG4ciEHn/9UpGhHTU4"
    "5kBVWltxoNlNdZuKiljcUKDpYbLl+FO6qcxC4ScqxUXA6aS8paWLxOmi5aDgzifpeQIcCKoOC333zd1wMoHB4DuMtt/45tzc/WlQ"
    "Wbj4jUXqqSFqgaGhsJfVzUUz6pQVMstTQmUeQGBXWY0UV6W4Ps8JgN54PIw7QdlSyyQaMZB8hnxkrwrbOqst2zq4iSI2cXzUQT4q"
    "IO2g/Qy3c9S64v2aowtaxWF2IKF86ZpfuDstzQcgdybvqipec/hb2UqWb2ZnHvYb2Bd4cHeX/5UnUvRTFknlUWe6elkBAbsnczyF"
    "0bIPpV0xTPVEBt9v0kaG/ljytZI1ZHt5DVn2Rqkh2+M1ZPAWr5mSLXi5WAFzVftTWWoZyZcMcs6oOD1BFLa2HwOiYZQjk+D235Cs"
    "jZ3LbKsDPw/apGJWg1XyHuyV1PX+D6R3V0pG3hhXafW/cen7RkYHdKNF0e8C3QOPNd/LkPoDXPJVxiZVSmSv4loYwT109za/37bX"
    "Pmi2kfioO2Q6dkE3fSTcR0eu+sbiIRr6HmZvD9wRsSM5YzHjWcHyXTFPmXJVjLhbYU8/5yNkepUIcyqwUIV3VKGiZrS/c5/PQPel"
    "PGxrs85VoIMUuTOQPGBH9QNmpQ3V6vM/N4PBYITZQSUC1I5IeCG/PAaA/AYl56eiB0F5oVFVVTzQ+A1LlnNwI3GXnej7DY++erll"
    "4DX3WFcMcZV42jOV63dMDTgk3E96mCJB7AvwygVkEJqXTwgBb1PQjlknfo7fyheLOEADSxkaY98QP1ur2ll6BWgphwny3pQa04Vh"
    "gGiSRwHiVpaSTHH/GRWexy91v9QUY+5Lv37y4nd06PatfoNGNgavneFj4H0izMurWNSBLl4pF7ZUjsShkbfSaJ0re+6Jav0MLbWh"
    "Sc6ymhFWT/PFhdsjrkif+PttzRAO8ztZgkV+E4s4bLG35bDFzbbDFmjuhWG90QyrW7oUhaPppsqO0Tdu626ED6OVXeRG7qbayKm6"
    "NjZz8t44KmEFYQA7N6hHwgnYd6k35RroOVWmpLhrC77d5WjuBlcmaMs5poowuY1zUEPcMCLFKmtIcphUe9u7l2Lteykl1Hp2wxop"
    "/yo8X2RaX9BD3uBLe3z8BAfd3ReFMpStxeKvv/yJWFlflxJKcjVQKfTiot0tMs9bkMjTWWBpT6lMUPauzNVluxNbWvLCcHExry5i"
    "umQpclXJDXd3+rGQGzyC8SAWya5KRnUP6KyUFH6ltXwjXVj1GWUD4C+5L+f06jFbDHn9HooMr/Pc49wIbzJ2dDU23IjD6OLQi6a8"
    "xbMGpSTW8sgifqPgDm8s3lLWk11SXD7pJYeosYm6uaPGVUdSBMLOA6qWrdJWBPi27TKB8mxtnpqy3LKAvB26paKtPASiGieRweHG"
    "oE7LSTtA//7l37Sve/teUfttaV4VjIRXFIpwy1ZQfQb/bosLubWiYDHuXhaCF5ap4ST3P2VpqWQoclA34nhhfqN0pUvJd13M3MfJ"
    "65TzzZenTuKnbP9hpwJl0Fxhpqzyud78Hqi6471fvHqHdydMny3jQcuePl3681SmVvD9VDu1O1VO7U5Lp3btK1CRz+ik8TQ7c5Fn"
    "ivlJHB4awbTvsekPlJzAC44KJ/POzWdfYmECNkIrb8qDfYIM+QO+YWeqt8bAsvm+F1+PjLjE6ihLJaTvRiB9wphHuY8qVY440tIO"
    "OxwtDr9fAl5nwTD+IIt6jPmhx4vlDwxAMweveVuOxE8M+AeVbgudkNvfO5j9JKqYnB+jKZ4Prppd4Ghj0/H1jDYqwi5WFaQphKtI"
    "KTpSoOoD/hsZ+iKur6+1RbDFCLC7bR3nstx+0N5F+9LaVS5Gh2cL6Jek9KsJiLm2Cbich9cDU/brGzB4fBulzGsumOe7fSPyxwA4"
    "a/pBU3zsG/m5KDFC/sDg5x7NYpoFr8Xii5QerbySq6gxXn1nvP3yFd7/Rj/f8CHsK7DL7+FSEYy8tcVF1vNU6BFDXINznmOcp5Uf"
    "55krgCzznVULLEDj9vqj6n2zBfw1UTFpECVH7veJO2U6XNy+VlvAgBjT71oRJKs17Vu33+hAMOVcoCUHhI4PiTvH6k4PFQWFO2ol"
    "MD5w904FRoBBd6tZtXgkBmy29xWsfJp/lgsiHcyT5lsHApap6L2jbrqAnbgmQlxjhI23LlranrOsk9hWIQlUxzM6oEG0ioj8woCN"
    "3eLVkheVh8AwxUHT024yNfxie0OCU4TkrPp4Le0/29efqMNSt4q2RE59ZA0jazJQ/fzAX79wMvscETmgtpsMY5XHt3E3hQsGIaOC"
    "fEQTDvMmw0VtOz5nv3SfE91iWnYfIhc0YzIIwP3/9s1XPI/ymp41sqorfmexZaN/OOAdcK8Wq099OqEFixOn1QfqaXXprT/N3Nr+"
    "Tp4TKpjpVYJecKqY5VWiWeUsO7/FQnKtrJ7kr7GnShJ/I6irrIBf5Y1H8PnJcJ7RFd/sT3DZRPEKJr833asnd/uiII43e3oLa20e"
    "t0A+8J+8KCnP4orkMhax8+Pxtkiw8dKCB9WQbL00w+S3EOAaFQRoJZq8PpfqbESZJhANqweVM3ulKkLgFNo9FEOW9xATliT4m2rY"
    "tGoLsUp48sFozo893VZVYPscC2PJ0c/ukKg4xkZZuC0n2Simxox1Xg5EZZ5bynUodyLqEvHAJD/YIkqjmKiOFbW2WLsDw2ulpmLH"
    "QOQ5+zL30VcPO/OH9mGrRUePde5HDXJ3p8r5NQUKmfZTFE1/Z2Nh9ZLyI1r081mPD2bpYj7c+X8ZXgHNGJ4AAA=="
)


def _page(b):
    return gzip.decompress(base64.b64decode("".join(b.split()))).decode("utf-8")


CINEMA_HTML = _page(_CINEMA_GZ)


def _studio():
    global _st
    if _st is None:
        _st = sys.modules.get("modules.studio") or importlib.import_module("modules.studio")
    if "conn" in _ctx and not _st._ready:
        _st._ctx.update(_ctx)
        _st._setup()
    return _st


def _setup():
    global _ready
    if _ready or "conn" not in _ctx:
        return
    _studio()
    with _ctx["lock"]:
        c = _ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS cinema_like(video TEXT,viewer TEXT,at REAL,PRIMARY KEY(video,viewer))")
        c.execute("CREATE TABLE IF NOT EXISTS cinema_comment(id INTEGER PRIMARY KEY AUTOINCREMENT,video TEXT,"
                  "viewer TEXT,name TEXT,text TEXT,at REAL,hidden INTEGER DEFAULT 0,flags INTEGER DEFAULT 0)")
        c.execute("CREATE INDEX IF NOT EXISTS cinema_comment_video ON cinema_comment(video,id)")
        c.execute("CREATE INDEX IF NOT EXISTS credit_unlock_video ON credit_unlock(video,at)")
        c.commit()
    _ready = True


def _limit(who, group, per_min, per_hour):
    t = time.time()
    k = group + "|" + who
    with _wins_lock:
        w = _wins[k]
        while w and w[0] < t - 3600:
            w.popleft()
        if len(w) >= per_hour or sum(1 for x in w if x > t - 60) >= per_min:
            return False
        w.append(t)
        if len(_wins) > 20000:
            for key in [x for x, v in _wins.items() if not v or v[-1] < t - 3600][:5000]:
                del _wins[key]
    return True


def _ip(h):
    try:
        xff = h.headers.get("X-Forwarded-For", "")
        return (xff.split(",")[0].strip() if xff else str(h.client_address[0]))[:64]
    except Exception:
        return "unknown"


def _ago(t):
    s = max(0, int(time.time() - (t or 0)))
    if s < 60:
        return "just now"
    if s < 3600:
        return "%dm ago" % (s // 60)
    if s < 86400:
        return "%dh ago" % (s // 3600)
    return "%dd ago" % (s // 86400)


def _rows(sql, args=()):
    with _ctx["lock"]:
        return _ctx["conn"].execute(sql, args).fetchall()


def _cards(rows):
    st = _studio()
    cols = st.COLS.split(",")
    return [st._public(dict(zip(cols, r))) for r in rows]


# ------------------------------------------------------------------ reads

def a_list(q, b, h):
    st = _studio()
    sort = str(q.get("sort") or "trending")
    term = CLEAN.sub("", str(q.get("q") or "")).strip()[:60]
    creator = CLEAN.sub("", str(q.get("creator") or "")).strip()[:40]
    try:
        off = max(0, min(5000, int(q.get("offset") or 0)))
    except ValueError:
        off = 0
    where, args = ["v.status='live'"], []
    if term:
        like = "%" + term.replace("%", "").replace("_", "") + "%"
        where.append("(v.title LIKE ? OR v.creator LIKE ? OR v.tags LIKE ?)")
        args += [like, like, like]
    if creator:
        where.append("(v.creator=? COLLATE NOCASE OR replace(v.creator,' ','_')=? COLLATE NOCASE)")
        args += [creator, creator]
    cols = ",".join("v." + c for c in st.COLS.split(","))
    sql = "SELECT " + cols + " FROM studio_video v WHERE " + " AND ".join(where)
    extra = []
    if sort == "new":
        sql += " ORDER BY v.live_at DESC"
    elif sort == "top":
        sql += " ORDER BY v.unlocks DESC, v.likes DESC, v.live_at DESC"
    else:
        sort = "trending"
        sql += (" ORDER BY (SELECT COUNT(*) FROM credit_unlock u WHERE u.video='st:'||v.id AND u.at>?)*3"
                " + v.likes + v.plays/20.0 DESC, v.live_at DESC")
        extra = [time.time() - 7 * 86400]
    rows = _rows(sql + " LIMIT ? OFFSET ?", tuple(args + extra + [PAGE + 1, off]))
    return {"sort": sort, "q": term, "creator": creator, "videos": _cards(rows[:PAGE]),
            "more": len(rows) > PAGE, "next": off + PAGE}, 200


def a_video(q, b, h):
    st = _studio()
    v = st._video(str(q.get("id") or ""))
    if not v or v["status"] != "live":
        return {"error": "not_found", "message": "That video isn't here any more."}, 404
    out = {"video": st._public(v)}
    viewer = str(q.get("viewer") or "")
    if VIEWER_RE.match(viewer):
        out["liked"] = bool(_rows("SELECT 1 FROM cinema_like WHERE video=? AND viewer=?", (v["id"], viewer)))
        out["can_comment"] = st._unlocked(v["id"], viewer)[0]
    return out, 200


def a_comments(q, b, h):
    vid = str(q.get("id") or "")
    if not ID_RE.match(vid):
        return {"comments": []}, 200
    rows = _rows("SELECT id,name,text,at FROM cinema_comment WHERE video=? AND hidden=0 ORDER BY id DESC LIMIT 100",
                 (vid,))
    return {"comments": [{"id": r[0], "name": r[1], "text": r[2], "ago": _ago(r[3])} for r in rows]}, 200


def a_leaders(q, b, h):
    rows = _rows("SELECT creator,SUM(unlocks),SUM(earned),SUM(status='live'),SUM(likes) FROM studio_video "
                 "WHERE status IN ('live','removed') GROUP BY creator COLLATE NOCASE "
                 "ORDER BY SUM(earned) DESC, SUM(unlocks) DESC LIMIT 25")
    out = []
    for r in rows:
        if not r[1] and not r[4]:
            continue
        proof = _rows("SELECT block_index FROM credit_unlock WHERE creator=? AND video LIKE 'st:%' "
                      "AND block_index IS NOT NULL ORDER BY id DESC LIMIT 1", (r[0],))
        blk = proof[0][0] if proof else None
        out.append({"creator": r[0], "paid_views": r[1] or 0, "earned_pence": r[2] or 0,
                    "videos": r[3], "likes": r[4] or 0,
                    "channel": SITE + "/cinema/@" + _studio()._slug(r[0]),
                    "proof_block": blk,
                    "proof": (SITE + "/x/walk/block?index=%s" % blk) if blk else None})
    tot = _rows("SELECT COALESCE(SUM(unlocks),0),COALESCE(SUM(earned),0),COUNT(DISTINCT creator) "
                "FROM studio_video WHERE status IN ('live','removed')")[0]
    return {"leaders": out, "total_paid_views": tot[0], "total_earned_pence": tot[1], "creators": tot[2]}, 200


def a_ticker(q, b, h):
    rows = _rows("SELECT u.creator,u.at,u.block_index,v.title,v.id FROM credit_unlock u "
                 "LEFT JOIN studio_video v ON v.id=substr(u.video,4) WHERE u.video LIKE 'st:%' "
                 "ORDER BY u.id DESC LIMIT 20")
    return {"ticker": [{"creator": r[0], "ago": _ago(r[1]), "block": r[2], "title": r[3] or "",
                        "id": r[4], "proof": (SITE + "/x/walk/block?index=%s" % r[2]) if r[2] else None}
                       for r in rows]}, 200


def a_creator(q, b, h):
    name = CLEAN.sub("", str(q.get("name") or "")).strip()[:40]
    if not name:
        return {"error": "not_found"}, 404
    r = _rows("SELECT creator,COALESCE(SUM(unlocks),0),COALESCE(SUM(earned),0),COALESCE(SUM(status='live'),0),"
              "COALESCE(SUM(likes),0) "
              "FROM studio_video WHERE (creator=? COLLATE NOCASE OR replace(creator,' ','_')=? COLLATE NOCASE) "
              "AND status IN ('live','removed')", (name, name))[0]
    if not r[0]:
        return {"error": "not_found", "message": "No channel called that yet."}, 404
    return {"creator": r[0], "paid_views": r[1], "earned_pence": r[2], "videos": r[3], "likes": r[4],
            "channel": SITE + "/cinema/@" + _studio()._slug(r[0])}, 200


# ------------------------------------------------------------------ writes

def a_like(q, b, h):
    st = _studio()
    v = st._video(str(b.get("id") or ""))
    viewer = str(b.get("viewer") or "")
    if not v or v["status"] != "live" or not VIEWER_RE.match(viewer):
        return {"error": "not_found"}, 404
    if not _limit(viewer, "like", 30, 400) or not _limit(_ip(h), "likeip", 60, 1500):
        return {"error": "slow_down"}, 429
    with _ctx["lock"]:
        c = _ctx["conn"]
        if c.execute("SELECT 1 FROM cinema_like WHERE video=? AND viewer=?", (v["id"], viewer)).fetchone():
            c.execute("DELETE FROM cinema_like WHERE video=? AND viewer=?", (v["id"], viewer))
            c.execute("UPDATE studio_video SET likes=MAX(0,likes-1) WHERE id=?", (v["id"],))
            liked = False
        else:
            c.execute("INSERT INTO cinema_like(video,viewer,at) VALUES(?,?,?)", (v["id"], viewer, time.time()))
            c.execute("UPDATE studio_video SET likes=likes+1 WHERE id=?", (v["id"],))
            liked = True
        n = c.execute("SELECT likes FROM studio_video WHERE id=?", (v["id"],)).fetchone()[0]
        c.commit()
    return {"liked": liked, "likes": n}, 200


def a_comment(q, b, h):
    st = _studio()
    v = st._video(str(b.get("id") or ""))
    viewer = str(b.get("viewer") or "")
    if not v or v["status"] != "live" or not VIEWER_RE.match(viewer):
        return {"error": "not_found"}, 404
    if not st._unlocked(v["id"], viewer)[0]:
        return {"error": "watch_first", "message": "Unlock the video to join the chat."}, 403
    name = CLEAN.sub("", str(b.get("name") or "")).strip()[:24]
    text = CLEAN.sub("", str(b.get("text") or "")).strip()[:400]
    if len(name) < 2:
        return {"error": "name", "message": "Add a name (2 letters or more)."}, 400
    if len(text) < 1:
        return {"error": "empty", "message": "Write something first."}, 400
    if not _limit(viewer, "comment", 2, 30) or not _limit(_ip(h), "commentip", 6, 120):
        return {"error": "slow_down", "message": "Easy - wait a few seconds between comments."}, 429
    with _ctx["lock"]:
        c = _ctx["conn"]
        cur = c.execute("INSERT INTO cinema_comment(video,viewer,name,text,at) VALUES(?,?,?,?,?)",
                        (v["id"], viewer, name, text, time.time()))
        c.execute("UPDATE studio_video SET comments=comments+1 WHERE id=?", (v["id"],))
        c.commit()
        cid = cur.lastrowid
    return {"posted": True, "comment": {"id": cid, "name": name, "text": text, "ago": "just now"}}, 200


def a_flag(q, b, h):
    try:
        cid = int(b.get("comment") or 0)
    except (TypeError, ValueError):
        return {"error": "bad"}, 400
    if not _limit(_ip(h), "flag", 5, 40):
        return {"received": True}, 200
    with _ctx["lock"]:
        c = _ctx["conn"]
        c.execute("UPDATE cinema_comment SET flags=flags+1,hidden=CASE WHEN flags+1>=3 THEN 1 ELSE hidden END "
                  "WHERE id=?", (cid,))
        c.commit()
    return {"received": True}, 200


def a_admin(q, b, h):
    key = os.environ.get("CREDITS_ADMIN_KEY", "").strip()
    if not key or not hmac.compare_digest(key, str(q.get("key") or "")):
        return {"error": "not_allowed"}, 403
    do = str(q.get("do") or "list")
    if do == "hide":
        try:
            cid = int(q.get("comment") or 0)
        except ValueError:
            return {"error": "bad"}, 400
        with _ctx["lock"]:
            _ctx["conn"].execute("UPDATE cinema_comment SET hidden=1 WHERE id=?", (cid,))
            _ctx["conn"].commit()
        return {"hidden": cid}, 200
    rows = _rows("SELECT id,video,name,text,flags,hidden,at FROM cinema_comment ORDER BY flags DESC, id DESC LIMIT 100")
    return {"comments": [{"id": r[0], "video": SITE + "/v/" + r[1], "name": r[2], "text": r[3], "flags": r[4],
                          "hidden": bool(r[5]), "ago": _ago(r[6]),
                          "hide": SITE + "/cinema/api/admin?key=KEY&do=hide&comment=%d" % r[0]} for r in rows]}, 200


GETS = {"list": a_list, "video": a_video, "comments": a_comments, "leaders": a_leaders,
        "ticker": a_ticker, "creator": a_creator, "admin": a_admin}
POSTS = {"like": a_like, "comment": a_comment, "flag": a_flag}


# ------------------------------------------------------------------ pages

def _esc(s):
    return html.escape(str(s or ""), quote=True)


def _render(path):
    st = _studio()
    boot = {"route": "wing", "site": SITE}
    title = "sebbi.pro Cinema — the 10p Wing"
    desc = "Watch creators' videos free, then 10p for the rest. No followers needed to earn. Every penny proven."
    image, video, url = "", None, SITE + "/cinema"
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 3 and parts[1] == "v":
        v = st._video(parts[2].lower())
        if v and v["status"] == "live":
            pub = st._public(v)
            boot.update({"route": "video", "video": pub})
            title = "%s — by %s · 10p Wing" % (v["title"], v["creator"])
            desc = "Watch the start free, then %s for the rest. 7p of every 10p goes to %s." % (
                pub["price_label"], v["creator"])
            image, url = SITE + pub["poster"], SITE + "/cinema/v/" + v["id"]
            if (v["teaser_mime"] or "").endswith("mp4"):
                video = SITE + pub["teaser"]
    elif len(parts) >= 2 and parts[1].startswith("@"):
        name = CLEAN.sub("", urllib.parse.unquote(parts[1][1:])).strip()[:40]
        boot.update({"route": "channel", "creator": name})
        title = "%s on the 10p Wing" % name
        desc = "Every video by %s. Watch free, then 10p for the rest." % name
        url = SITE + "/cinema/@" + _studio()._slug(name)
    elif len(parts) >= 2 and parts[1] == "governance":
        boot["route"] = "gov"
    og = ['<title>%s</title>' % _esc(title),
          '<meta name="description" content="%s">' % _esc(desc),
          '<meta property="og:site_name" content="sebbi.pro">',
          '<meta property="og:title" content="%s">' % _esc(title),
          '<meta property="og:description" content="%s">' % _esc(desc),
          '<meta property="og:url" content="%s">' % _esc(url),
          '<meta property="og:type" content="%s">' % ("video.other" if video else "website"),
          '<meta name="twitter:card" content="summary_large_image">',
          '<meta name="twitter:title" content="%s">' % _esc(title),
          '<meta name="twitter:description" content="%s">' % _esc(desc)]
    if boot["route"] == "video":
        og += ['<meta property="og:image" content="%s">' % _esc(image),
               '<meta name="twitter:image" content="%s">' % _esc(image)]
    if video:
        og += ['<meta property="og:video" content="%s">' % _esc(video),
               '<meta property="og:video:secure_url" content="%s">' % _esc(video),
               '<meta property="og:video:type" content="video/mp4">']
    data = json.dumps(boot).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return CINEMA_HTML.replace("<!--OG-->", "\n".join(og)).replace("__BOOT__", data).encode("utf-8")


# ------------------------------------------------------------------ transport

def _send(h, obj, code=200):
    body = json.dumps(obj).encode("utf-8")
    h.send_response(code)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Cache-Control", "no-store")
    h.end_headers()
    h.wfile.write(body)


def _serve(h, method):
    u = urllib.parse.urlparse(h.path)
    path = u.path.rstrip("/") or "/"
    if path != "/cinema" and not path.startswith("/cinema/"):
        return False
    if "conn" not in _ctx:
        _send(h, {"error": "not_armed", "message": "Open /x/cinema/status once."}, 503)
        return True
    _setup()
    q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
    if path.startswith("/cinema/api/"):
        name = path[12:].strip("/")
        table = GETS if method == "GET" else POSTS
        fn = table.get(name)
        if not fn:
            _send(h, {"error": "not_found"}, 404)
            return True
        body = {}
        if method == "POST":
            try:
                n = min(int(h.headers.get("Content-Length") or 0), 20000)
                raw = h.rfile.read(n) if n else b""
                body = json.loads(raw.decode("utf-8") or "{}")
                if not isinstance(body, dict):
                    body = {}
            except Exception:
                body = {}
        try:
            out, code = fn(q, body, h)
        except Exception as e:
            print("CINEMA ERR %s: %s" % (name, e), flush=True)
            out, code = {"error": "failed"}, 500
        _send(h, out, code)
        return True
    if method != "GET":
        return False
    body = _render(path)
    h.send_response(200)
    h.send_header("Content-Type", "text/html; charset=utf-8")
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Cache-Control", "no-cache")
    h.end_headers()
    h.wfile.write(body)
    return True


def _find_handler_class(ctx):
    if isinstance(ctx, dict):
        for k in ("handler_class", "handler", "Handler", "h", "request_handler"):
            v = ctx.get(k)
            if v is None:
                continue
            cls = v if isinstance(v, type) else type(v)
            if hasattr(cls, "do_GET"):
                return cls
    f = sys._getframe()
    while f is not None:
        s = f.f_locals.get("self")
        if s is not None and hasattr(type(s), "do_GET") and hasattr(s, "wfile"):
            return type(s)
        f = f.f_back
    return None


def _install(ctx):
    global _patched
    if isinstance(ctx, dict) and "conn" in ctx:
        _ctx.update(ctx)
        _setup()
    if _patched:
        return True
    cls = _find_handler_class(ctx)
    if cls is None:
        return False
    if getattr(cls, "_cinema3_patched", False):
        _patched = True
        return True
    og = cls.do_GET
    op = getattr(cls, "do_POST", None)

    def do_GET(self):
        try:
            if _serve(self, "GET"):
                return
        except (BrokenPipeError, ConnectionResetError):
            return
        return og(self)

    def do_POST(self):
        try:
            if _serve(self, "POST"):
                return
        except (BrokenPipeError, ConnectionResetError):
            return
        return op(self) if op else None

    cls.do_GET = do_GET
    if op:
        cls.do_POST = do_POST
    cls._cinema3_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install(ctx)
    counts = {}
    if "conn" in _ctx:
        try:
            r = _rows("SELECT COUNT(*),COALESCE(SUM(unlocks),0),COALESCE(SUM(likes),0),COALESCE(SUM(comments),0) "
                      "FROM studio_video WHERE status='live'")[0]
            counts = {"videos": r[0], "paid_views": r[1], "likes": r[2], "comments": r[3]}
        except Exception:
            pass
    return {"module": "cinema", "version": VERSION, "armed": armed,
            "serves": ["/cinema", "/cinema/v/<id>", "/cinema/@<name>", "/cinema/api/*"],
            "counts": counts, "wing": SITE + "/cinema"}, 200
