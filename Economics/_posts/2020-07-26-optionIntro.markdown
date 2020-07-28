---
layout: post 
title:  "Option introduction"
date:   2020-07-27 02:58:18 +09:00
categories: Economics Finance
---
<div style="color:black;font-size:24px;">
  정의 
</div>

  > 기초자산을 만기시점에 행사가격으로 사고 팔수 있는 권리를 주고 받는 계약

  - 옵션을 매수(Long position) 하는 사람은 '권리'를 사는 사람,<br> 
  - 옵션을 매도(Short position) 하는 사람은 '권리'의 반대 급부에 해당하는 '의무'를 지게됨

  - 옵션은 미래에 거래할 수 있는 '권리'를 사는 것이기 때문에, 권리는 행사할 수 있지만, 불리한 상황에서는 행사하지 않을 수 도 있다.

<br>

<div style="color:black;font-size:24px;">
  옵션 예시
  <br>
</div>

  > 2020/07/27 시점에 **'KOSPI200'** 에 대해서 **'8월 13일'**에 **'295'** 가격으로 **'살수있는 권리'** 를 구매한다.

  - KOSPI200: 기초자산
  - 8월 13일 : 만기일
  - 295 : 행사 가격
  - 살수있는 권리 : Call option

<br>

<div style="color:black;font-size:24px;">
  만기일(T 시점에서의 옵션 손익 구조)
  <br>
</div>
  
![옵션 손익 구조](/assets/economics/option/option_payoff.png)
<br>
<br>
<span style="color:black;font-size:24px;">
  Put call parity
</span>

 - 만기일 시점에서, 콜 옵션 + 무위험 채권의 가치는 풋 옵션 + 주식의 가치와 동일하다 는 것을 이용.
 - 각 포트폴리오의 수익 구조(여기서 X는 행사 금액을 뜻함)
 
 ![옵션 손익 구조](/assets/economics/option/put_call_parity.png)

 - 따라서 만기일에는 다음과 같은 식이 성립한다.<br>
 > \\( c_T + K = p_T + S_T \\)<br>
 > where <br>
 > &nbsp;&nbsp;&nbsp;&nbsp;\\( c_T: T\\) 시점 콜 옵션 가격<br>
 > &nbsp;&nbsp;&nbsp;&nbsp;\\( p_T: T\\) 시점 풋 옵션 가격<br>
 > &nbsp;&nbsp;&nbsp;&nbsp;\\( S_T: T\\) 시점 주식 가격<br>
 > &nbsp;&nbsp;&nbsp;&nbsp;\\( K:\\) 만기 시점 행사가<br>

 - 현재 시점으로 치환 했을 때는 다음의 식이 성립한다.<br>
  > \\( c_0 + Ke^{-rT} = p_0 + S_0 \\)<br>
 > where <br>
 > &nbsp;&nbsp;&nbsp;&nbsp;\\( c_0: \\) 현재 시점 콜 옵션 가격<br>
 > &nbsp;&nbsp;&nbsp;&nbsp;\\( p_0: \\) 현재 시점 풋 옵션 가격<br>
 > &nbsp;&nbsp;&nbsp;&nbsp;\\( S_0: \\) 현재 시점 주식 가격<br>
 > &nbsp;&nbsp;&nbsp;&nbsp;\\( K:\\) 만기 시점 행사가<br>

<br>
<br>
<span style="color:black;font-size:24px;">
  옵션 가격에 영향을 끼치는 변수 정리
</span>
 1. 기초자산 가격 :\\( S_t \\)
 1. 기초자산의 변동성 : \\( \sigma_S \\)
 1. 잔존 만기일 : \\( T-t \\)
 1. 무위험 이자율 : \\( r_f \\)
 1. 행사가격 : \\( K \\)