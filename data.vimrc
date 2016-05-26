set nowrap
set showcmd
set nosol
set ve=all

hi ColorColumn ctermbg=lightgreen
set cursorline cursorcolumn
"hi CursorColumn ctermbg=lightblue
hi CursorColumn ctermfg=red

set isk=@,48-57,124,192-255

map ,0 mx:%s/0/_/g:nohl`x
map ,1 mx:%s/_/0/g:nohl`x

map ,7 :set cc=1,17,33,49,65,81,97,113,129,145,161,177,193,209,225,241,257,273,289,305,321,337,353,369,385,401,417,433,449,465,481,497,513,529,545,561,577,593,609,625,641,657,673,689,705,721,737,753,769,785,801,817,833,849,865,881,897,913,929,945,961,977,993
map ,8 :set cc=1,33,65,97,129,161,193,225,257,289,321,353,385,417,449,481,513,545,577,609,641,673,705,737,769,801,833,865,897,929,961,993
map ,9 :set cc=93,126,159,192,225,258,291,324,357,390,423,456,489,522,555,588,621,654,687,720,753,786,819,852,885,918,951,984
"seq -s , 94 33 999

map ,p :%s/ //g:%s/^\[//g:%s/]$//:%s/0/_/g:%!grep 11G/\|_*1_*\|

function! DoSort() range abort
  let col = col(".")
  execute "%! sort -t '' -k 1.".col
endfunction

map ,s mx:call DoSort()`x

function! DoCol() range abort
  let col = col(".")
"  if &colorcolumn != ''
"    setlocal colorcolumn&
"  else
    let &l:colorcolumn = col
"  endif
endfunction

map ,c mx:call DoCol()`x
