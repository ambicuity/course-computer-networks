# TI-LFA Backup Report

| PLR | Failed | Type | Backup Path | Segments |
|---|---|---|---|---|
| KCMO | KCMO-STL | link | KCMO -> STL -> MEM -> ATL | 16009, 16008 |
| STL | STL-MEM | link | STL -> IND -> BNA -> ATL | 16011, 16007 |
| MEM | MEM-ATL | link | MEM -> BNA -> ATL | 16007 |
| KCMO | STL | node | KCMO -> OKC -> DAL -> ATL | 16002, 16003 |
| KCMO | MEM | node | KCMO -> STL -> IND -> BNA -> ATL | 16009, 16011, 16007 |
| KCMO | KCMO-STL | link | KCMO -> STL -> MEM -> ATL -> MIA | 16009, 16008, 16005 |
| STL | STL-MEM | link | STL -> IND -> BNA -> ATL -> MIA | 16011, 16007, 16005 |
| MEM | MEM-ATL | link | MEM -> BNA -> ATL -> MIA | 16007, 16005 |
| ATL | ATL-MIA | link | ATL -> HOU -> MIA | 16004 |
| KCMO | STL | node | KCMO -> OKC -> DAL -> HOU -> MIA | 16002, 16003, 16004 |
| KCMO | MEM | node | KCMO -> OKC -> DAL -> HOU -> MIA | 16002, 16003, 16004 |
| KCMO | ATL | node | KCMO -> OKC -> DAL -> HOU -> MIA | 16002, 16003, 16004 |
| DAL | DAL-ATL | link | DAL -> MEM -> ATL | 16008 |
| DAL | DAL-HOU | link | DAL -> ATL -> MIA | 16005 |
| HOU | HOU-MIA | link | HOU -> MIA | 16006 |
| DAL | HOU | node | DAL -> ATL -> MIA | 16005 |
| CHI | CHI-KCMO | link | CHI -> STL -> MEM -> DAL -> HOU | 16009, 16008, 16003 |
| KCMO | KCMO-OKC | link | KCMO -> DAL -> HOU | 16003 |
| OKC | OKC-DAL | link | OKC -> HOU | 16004 |
| DAL | DAL-HOU | link | DAL -> OKC -> HOU | 16002 |
| CHI | KCMO | node | CHI -> STL -> MEM -> DAL -> HOU | 16009, 16008, 16003 |
| CHI | OKC | node | CHI -> KCMO -> DAL -> HOU | 16001, 16003 |
| CHI | DAL | node | CHI -> KCMO -> OKC -> HOU | 16001, 16002 |
| CHI | CHI-IND | link | CHI -> IND -> BNA -> ATL -> MIA | 16011, 16007, 16005 |
| IND | IND-BNA | link | IND -> STL -> MEM -> ATL -> MIA | 16009, 16008, 16005 |
| BNA | BNA-ATL | link | BNA -> MEM -> ATL -> MIA | 16008, 16005 |
| ATL | ATL-MIA | link | ATL -> HOU -> MIA | 16004 |
| CHI | IND | node | CHI -> STL -> MEM -> ATL -> MIA | 16009, 16008, 16005 |
| CHI | BNA | node | CHI -> STL -> MEM -> ATL -> MIA | 16009, 16008, 16005 |
| CHI | ATL | node | CHI -> KCMO -> OKC -> DAL -> HOU -> MIA | 16001, 16002, 16003, 16004 |
