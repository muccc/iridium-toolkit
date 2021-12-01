SRC=bch.py fec.py rs.py rs6.py reedsolo.py reedsolo6.py
GEN=parser.py

do: ${SRC} ${GEN} run

.FORCE:

${SRC}: .FORCE
	cp ../$@ .

parser.py: .FORCE
	./mkmodule.pl <../iridium-parser.py > $@

run:
	pytest-3 test_parser.py
	
clean:
	for file in ${SRC} ${GEN}; do ${RM} $$file $${file}c ; done
	${RM} -r __pycache__
	


	
