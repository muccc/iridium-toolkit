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

map ,p :%s/ //g:%s/^\[//g:%s/]$//:%s/0/_/g/^[^1]*$:.,$!uniq -c 1G/^[_\|]*1[_\|]*\|

function! DoSort() range abort
  let col = col(".")
  execute "%! sort -t '' -k 1.".col
endfunction

map ,s mx:call DoSort()`x

function! DoCol() range abort
  let col = col(".")
  let &l:colorcolumn = col
  echo "marking" col
endfunction

function! DoVisCol() range abort
  let [lnum1, col1] = getpos("'<")[1:2]
  let [lnum2, col2] = getpos("'>")[1:2]
  let &l:colorcolumn = join(range(col1,999,col2-col1+1),',')
  echo "start @" col1 "repeat" (col2-col1+1)
endfunction

nnoremap ,c :call DoCol()<CR>
vnoremap ,c mx:call DoVisCol()<CR>`x

"function! Pcol(...) abort
"  let a:above = get(a:, 1, 0)
"  let l:col = virtcol('.')
"  execute 'normal!' a:above ? 'P' : 'p'
"  call cursor('.', l:col)
"endfunction

function! Pcol() abort
  let l:col = virtcol('.')
  execute 'normal!' 'p'
  call cursor('.', l:col)
endfunction
function! Pcolup() abort
  let l:col = virtcol('.')
  execute 'normal!' 'P'
  call cursor('.', l:col)
endfunction

nnoremap <silent> p :call Pcol()<CR>
nnoremap <silent> P :call Pcolup()<CR>

" stay in column while creating a new line
nnoremap <silent> o mxo`xji
