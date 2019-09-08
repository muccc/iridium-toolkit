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

map ,7 :let &l:colorcolumn = join(range(1,999,16),',')
map ,8 :let &l:colorcolumn = join(range(1,999,32),',')
map ,9 :let &l:colorcolumn = join(range(93,999,33),',')

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
