set nowrap
set showcmd
set nosol
set ve=all

"seq -s , 87 33 999
set cc=86,119,152,185,218,251,284,317,350,383,416,449,482,515,548,581,614,647,680,713,746,779,812,845,878,911,944,977
hi ColorColumn ctermbg=lightgreen
set cursorline cursorcolumn
"hi CursorColumn ctermbg=lightblue
hi CursorColumn ctermfg=red

map ,0 mx:%s/0/_/g:nohl`x
map ,1 mx:%s/_/0/g:nohl`x
